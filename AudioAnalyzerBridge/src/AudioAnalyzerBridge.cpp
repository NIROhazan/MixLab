#include "AudioAnalyzerBridge.h"
#include "BPM_Detector.h"
#include "LoadAudioFunction.h"
#include "FFT_Processor.h"
#include "dr_wav.h"
#include <iostream>
#include <vector>
#include <memory>
#include <algorithm>
#include <string>
#include <cstdio>  // For file operations
#include <complex>

// Platform-specific includes
#ifdef _WIN32
#define NOMINMAX                // Prevent Windows.h from defining min/max macros
#define _CRT_SECURE_NO_WARNINGS // Enable _wfopen and other functions
    #include <windows.h>            // For WideCharToMultiByte and file operations
#else
    #include <codecvt>
    #include <filesystem> // For modern file operations (C++17)
#endif

// Global variables to store state
static std::unique_ptr<BPM_Detector> g_bpmDetector;
static std::unique_ptr<LoadAudioFunction> g_loadAudio;
static std::unique_ptr<FFT_Processor> g_fftProcessor;
static std::vector<size_t> g_lastDetectedBeats;
static int g_lastBPM = 0;
static std::wstring g_originalFilePath;        // Store the original file path
static float g_originalLength;                 // Store the original file length
static int g_originalBPM = 0;                  // Store the original file's BPM
static int g_currentBPM = 0;                   // Store the current BPM we're at
static float g_cumulativeStretchFactor = 1.0f; // Track cumulative stretch

// Cross-platform file operation helpers
static bool fileExists(const std::wstring &filePath)
{
#ifdef _WIN32
    HANDLE fileHandle = CreateFileW(filePath.c_str(), GENERIC_READ, FILE_SHARE_READ,
                                    NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (fileHandle == INVALID_HANDLE_VALUE)
    {
        return false;
    }
    CloseHandle(fileHandle);
    return true;
#else
    try
    {
        std::wstring_convert<std::codecvt_utf8<wchar_t>> converter;
        std::string narrowPath = converter.to_bytes(filePath);
        return std::filesystem::exists(narrowPath);
    }
    catch (const std::exception &)
    {
        return false;
    }
#endif
}


/**
 * @brief Saves audio data to a WAV file.
 *
 * Converts a vector of float audio samples to 16-bit PCM and writes them to a WAV file with the specified sample rate and number of channels.
 *
 * @param filename      The output file path (wide string, Windows-specific).
 * @param audio         The audio data to save (mono, normalized floats).
 * @param sampleRate    The sample rate of the audio in Hz.
 * @param numChannels   The number of audio channels (default is 1).
 * @return True if the file was saved successfully, false otherwise.
 */
static bool saveAudioToFile(const wchar_t *filename, const std::vector<float> &audio, unsigned int sampleRate, unsigned short numChannels = 1)
{
    // Configure a 16-bit PCM WAV output
    drwav_data_format format{};
    format.container = drwav_container_riff;
    format.format = DR_WAVE_FORMAT_PCM;
    format.channels = numChannels;
    format.sampleRate = sampleRate;
    format.bitsPerSample = 16;

    drwav wav{};

#ifdef _WIN32
    if (!drwav_init_file_write_w(&wav, filename, &format, nullptr))
    {
        return false;
    }
#else
    // Convert wide path to UTF-8 and open on non-Windows
    std::string narrowFilename;
    try
    {
        std::wstring_convert<std::codecvt_utf8<wchar_t>> converter;
        narrowFilename = converter.to_bytes(filename);
    }
    catch (...)
    {
        return false;
    }

    if (!drwav_init_file_write(&wav, narrowFilename.c_str(), &format, nullptr))
    {
        return false;
    }
#endif

    // Convert float samples [-1, 1] to 16-bit PCM
    const size_t totalSamples = audio.size();
    std::vector<int16_t> pcm(totalSamples);
    for (size_t i = 0; i < totalSamples; ++i)
    {
        float s = audio[i];
        if (s > 1.0f)
            s = 1.0f;
        else if (s < -1.0f)
            s = -1.0f;
        const int value = static_cast<int>(s * 32767.0f);
        pcm[i] = static_cast<int16_t>(value);
    }

    const drwav_uint64 framesToWrite = (numChannels > 0) ? static_cast<drwav_uint64>(totalSamples / numChannels) : 0;
    const drwav_uint64 framesWritten = drwav_write_pcm_frames(&wav, framesToWrite, pcm.data());
    drwav_uninit(&wav);
    return framesWritten == framesToWrite;
}

extern "C"
{
    /**
     * @brief Initializes the Audio Analyzer Bridge and its core components.
     *
     * Allocates and initializes the BPM detector, audio loader, and FFT processor.
     *
     * @return True if initialization was successful, false otherwise.
     */
    AUDIO_ANALYZER_BRIDGE_API bool InitializeAudioAnalyzerBridge()
    {
        try
        {
            g_bpmDetector.reset(new BPM_Detector());
            g_loadAudio.reset(new LoadAudioFunction());
            g_fftProcessor.reset(new FFT_Processor());

            return true;
        }
        catch (...)
        {
            return false;
        }
    }


    /**
     * @brief Loads audio data from a file for waveform display or tempo change.
     *
     * Loads the full audio file at full quality for waveform visualization or tempo processing.
     *
     * @param filename   The input file path (wide string).
     * @param outData    Pointer to the output buffer (allocated inside the function).
     * @param length     Pointer to store the number of samples loaded.
     * @param sampleRate Pointer to store the sample rate of the audio.
     * @return True if the audio was loaded successfully, false otherwise.
     */
    AUDIO_ANALYZER_BRIDGE_API bool LoadAudioFull(const wchar_t *filename, float **outData, unsigned int *length, unsigned int *sampleRate)
    {
        try
        {
            if (!g_loadAudio)
            {
                return false;
            }

            // Load the audio file with full quality for waveform
            std::vector<float> samples = g_loadAudio->loadAudioAtOriginalRate(filename, *sampleRate, 0.0f);

            // Allocate memory for the output data
            *length = static_cast<unsigned int>(samples.size());
            *outData = new float[samples.size()];

            // Copy the data to the output buffer
            std::copy(samples.begin(), samples.end(), *outData);

            return true;
        }
        catch (...)
        {
            return false;
        }
    }

    /**
     * @brief Analyzes the BPM of an audio file.
     *
     * Loads the audio, detects onsets and beats, and estimates the tempo in BPM.
     *
     * @param filename The input file path (wide string).
     * @return The estimated BPM, or 0 if analysis failed.
     */
    AUDIO_ANALYZER_BRIDGE_API int AnalyzeFileBPM(const wchar_t *filename)
    {
        try
        {
            if (!g_bpmDetector || !g_loadAudio)
            {
                return 0;
            }

            // Load the audio file
            unsigned int sampleRate;
            std::vector<float> samples = g_loadAudio->loadAudio(filename, sampleRate, 30.0f);

            // Process the audio
            const unsigned int hopSize = 512;
            std::vector<float> onsetFunction = g_bpmDetector->detectOnsets(samples, sampleRate);
            g_lastDetectedBeats = g_bpmDetector->findBeats(onsetFunction);

            if (g_lastDetectedBeats.empty())
            {
                return 0;
            }

            // Calculate BPM
            g_lastBPM = g_bpmDetector->estimateTempo(g_lastDetectedBeats, sampleRate, hopSize);
            return g_lastBPM;
        }
        catch (...)
        {
            return 0;
        }
    }

    /**
     * @brief Analyzes the full track to detect all beat positions.
     *
     * Loads the entire audio file, detects onsets and beats, and returns all beat positions and the sample rate.
     *
     * @param filename     The input file path (wide string).
     * @param beatPositions Pointer to an array that will be allocated and filled with beat positions.
     * @param numBeats     Pointer to store the number of detected beats.
     * @param sampleRate   Pointer to store the sample rate of the audio.
     * @return True if analysis was successful, false otherwise.
     */
    AUDIO_ANALYZER_BRIDGE_API bool AnalyzeFullTrackBeats(const wchar_t *filename, int **beatPositions, int *numBeats, unsigned int *sampleRate)
    {
        try
        {
            if (!g_bpmDetector || !g_loadAudio || !beatPositions || !numBeats || !sampleRate)
            {
                return false;
            }

            // Load the full audio file using loadAudioAtOriginalRate (no time limit)
            unsigned int fullSampleRate;
            std::vector<float> fullSamples = g_loadAudio->loadAudioAtOriginalRate(filename, fullSampleRate, 0.0f);

            if (fullSamples.empty())
            {
                *numBeats = 0;
                *beatPositions = nullptr;
                *sampleRate = 0;
                return false;
            }

            // Process the full audio for onset detection
            const unsigned int hopSize = 768;
            std::vector<float> onsetFunction = g_bpmDetector->detectOnsets(fullSamples, fullSampleRate);
            std::vector<size_t> fullBeats = g_bpmDetector->findBeats(onsetFunction);

            if (fullBeats.empty())
            {
                *numBeats = 0;
                *beatPositions = nullptr;
                *sampleRate = fullSampleRate;
                return true; // Not an error, just no beats found
            }

            // Allocate memory for beat positions
            *numBeats = static_cast<int>(fullBeats.size());
            *beatPositions = new int[*numBeats];
            *sampleRate = fullSampleRate;

            // Copy beat positions
            for (int i = 0; i < *numBeats; i++)
            {
                (*beatPositions)[i] = static_cast<int>(fullBeats[i]);
            }

            std::cout << "Full track analysis complete: " << *numBeats << " beats detected in "
                      << fullSamples.size() / fullSampleRate << " seconds" << std::endl;

            return true;
        }
        catch (const std::exception &e)
        {
            std::cout << "Error in AnalyzeFullTrackBeats: " << e.what() << std::endl;
            *numBeats = 0;
            *beatPositions = nullptr;
            return false;
        }
        catch (...)
        {
            std::cout << "Unknown error in AnalyzeFullTrackBeats" << std::endl;
            *numBeats = 0;
            *beatPositions = nullptr;
            return false;
        }
    }

    /**
     * @brief Frees memory allocated for beat positions.
     *
     * @param beatPositions Pointer to the array of beat positions to free.
     */
    AUDIO_ANALYZER_BRIDGE_API void FreeBeatPositions(int *beatPositions)
    {
        if (beatPositions)
        {
            delete[] beatPositions;
        }
    }


    /**
     * @brief Changes the tempo of an audio file using FFT-based time stretching.
     *
     * Loads the original audio, applies time stretching, and saves the result to a new file.
     *
     * @param inputFile     The input file path (wide string).
     * @param outputFile    The output file path (wide string).
     * @param stretchFactor The factor by which to stretch the tempo (e.g., 1.2 for 20% faster).
     * @param length        The length of the audio to process (in seconds).
     * @return True if the tempo change was successful, false otherwise.
     */
    AUDIO_ANALYZER_BRIDGE_API bool ChangeTempoWithFFT(const wchar_t *inputFile, const wchar_t *outputFile, float stretchFactor, float length)
    {
        try
        {
            // Validate input parameters
            if (!inputFile || !outputFile)
            {
                std::cout << "Error: Invalid input or output file path" << std::endl;
                return false;
            }

            // Validate components
            if (!g_loadAudio || !g_fftProcessor)
            {
                std::cout << "Error: Components not initialized properly" << std::endl;
                return false;
            }

            std::cout << "Debug: Loading audio file..." << std::endl;

            // Check if this is a new original file
            bool isNewFile = g_originalFilePath.empty() ||
                             std::wstring(inputFile) != g_originalFilePath;

            if (isNewFile)
            {
                // Store original file info
                g_originalFilePath = inputFile;
                g_originalLength = length;
                g_cumulativeStretchFactor = 1.0f;

                // Analyze original BPM if we have a BPM detector
                if (g_bpmDetector)
                {
                    g_originalBPM = AnalyzeFileBPM(inputFile);
                    g_currentBPM = g_originalBPM;
                }
            }

            // Always proceed with loading and processing unless exactly 1.0

            // Verify original file exists and is accessible
            if (!fileExists(g_originalFilePath))
            {
                std::wcout << L"Error: Cannot access original file: " << g_originalFilePath << std::endl;
                g_originalFilePath.clear();
                return false;
            }

            // Always load from the original file for processing
            unsigned int sampleRate;
            std::vector<float> samples = g_loadAudio->loadAudioAtOriginalRate(g_originalFilePath.c_str(), sampleRate, g_originalLength);

            if (samples.empty())
            {
                std::cout << "Error: Failed to load original audio for processing" << std::endl;
                return false;
            }

            std::cout << "Debug: Processing tempo change from original file" << std::endl;
            std::cout << "Input file: " << g_originalFilePath.c_str() << std::endl;
            std::cout << "Stretch factor: " << stretchFactor << std::endl;

            // Process the audio using FFT phase vocoder time stretching
            // The third argument (windowSize) is optional in the header and defaults to 2048
            std::vector<float> stretchedSamples = g_fftProcessor->timeStretch(samples, stretchFactor);

            if (stretchedSamples.empty())
            {
                std::cout << "Error: Time stretching produced no output" << std::endl;
                return false;
            }

            // Save the processed audio
            if (!saveAudioToFile(outputFile, stretchedSamples, sampleRate))
            {
                std::cout << "Error: Failed to save processed audio" << std::endl;
                return false;
            }

            std::cout << "Successfully processed tempo change" << std::endl;
            return true;
        }
        catch (const std::exception &e)
        {
            std::cout << "Error in ChangeTempoWithFFT: " << e.what() << std::endl;
            return false;
        }
        catch (...)
        {
            std::cout << "Unknown error in ChangeTempoWithFFT" << std::endl;
            return false;
        }
    }

    /**
     * @brief Cleans up and releases all resources used by the Audio Analyzer.
     *
     * Resets all global components, clears state, and deletes any temporary files.
     */
    AUDIO_ANALYZER_BRIDGE_API void CleanupAudioAnalyzer()
    {
        g_bpmDetector.reset();
        g_loadAudio.reset();
        g_fftProcessor.reset();
        g_lastDetectedBeats.clear();
        g_lastBPM = 0;
        g_originalFilePath.clear();
        g_originalLength = 0.0f;
        g_originalBPM = 0;
        g_currentBPM = 0;
        g_cumulativeStretchFactor = 1.0f;
    }

    AUDIO_ANALYZER_BRIDGE_API bool GetHanningWindow(unsigned int size, float *outWindow)
    {
        if (!g_fftProcessor || size == 0 || !outWindow)
        {
            return false;
        }

        try
        {
            std::vector<float> window = g_fftProcessor->hanningWindow(size);

            // Copy the window data to the output buffer
            for (unsigned int i = 0; i < size; ++i)
            {
                outWindow[i] = window[i];
            }

            return true;
        }
        catch (const std::exception &e)
        {
            std::cerr << "Error generating Hanning window: " << e.what() << std::endl;
            return false;
        }
    }

    AUDIO_ANALYZER_BRIDGE_API bool PerformFFTWithMagnitudes(const float *audioData, unsigned int length, float *magnitudes)
    {
        if (!g_fftProcessor || !audioData || !magnitudes || length == 0)
        {
            return false;
        }

        // Check if length is a power of 2
        if ((length & (length - 1)) != 0)
        {
            std::cerr << "FFT length must be a power of 2" << std::endl;
            return false;
        }

        try
        {
            // Convert input to complex numbers
            std::vector<std::complex<float>> complexData(length);
            for (unsigned int i = 0; i < length; ++i)
            {
                complexData[i] = std::complex<float>(audioData[i], 0.0f);
            }

            // Perform FFT
            g_fftProcessor->FFT(complexData);

            // Calculate magnitudes directly in C++
            // For real input, we only need the first half + 1 (DC and positive frequencies)
            unsigned int numMagnitudes = length / 2 + 1;

            for (unsigned int i = 0; i < numMagnitudes; ++i)
            {
                magnitudes[i] = std::abs(complexData[i]);
            }

            return true;
        }
        catch (const std::exception &e)
        {
            std::cerr << "Error in FFT with magnitudes: " << e.what() << std::endl;
            return false;
        }
    }

    AUDIO_ANALYZER_BRIDGE_API bool ProcessSpectrogram(
        const float *spectrogramData,
        unsigned int width,
        unsigned int height,
        float *processedData,
        float dynamicRangeDb,
        float gamma)
    {
        if (!spectrogramData || !processedData || width == 0 || height == 0)
        {
            return false;
        }

        try
        {
            const unsigned int totalElements = width * height;

            // Step 1: Apply logarithmic scaling
            for (unsigned int i = 0; i < totalElements; ++i)
            {
                processedData[i] = std::log10(spectrogramData[i] + 1e-10f);
            }

            // Step 2: Calculate percentiles for dynamic range compression
            std::vector<float> sortedData(processedData, processedData + totalElements);
            std::sort(sortedData.begin(), sortedData.end());

            // Calculate 1st and 99th percentiles
            unsigned int p1Index = static_cast<unsigned int>(totalElements * 0.01f);
            unsigned int p99Index = static_cast<unsigned int>(totalElements * 0.99f);

            float p1 = sortedData[p1Index];
            float p99 = sortedData[p99Index];

            // Step 3: Apply dynamic range compression
            float rangeMin = p99 - dynamicRangeDb / 10.0f;
            float rangeMax = p99;
            float range = rangeMax - rangeMin;

            if (range < 1e-6f)
                range = 1e-6f; // Avoid division by zero

            for (unsigned int i = 0; i < totalElements; ++i)
            {
                // Clip to range
                float clipped = (std::max)(rangeMin, (std::min)(processedData[i], rangeMax));
                // Normalize
                processedData[i] = (clipped - rangeMin) / range;
            }

            // Step 4: Apply gamma correction
            for (unsigned int i = 0; i < totalElements; ++i)
            {
                processedData[i] = std::pow(processedData[i], static_cast<float>(gamma));
            }

            // Step 5: Scale to 0-255 range
            for (unsigned int i = 0; i < totalElements; ++i)
            {
                processedData[i] = (std::max)(0.0f, (std::min)(255.0f, processedData[i] * 255.0f));
            }

            return true;
        }
        catch (const std::exception &e)
        {
            std::cerr << "Error in spectrogram processing: " << e.what() << std::endl;
            return false;
        }
    }
}