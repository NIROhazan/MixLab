#pragma once

// Cross-platform API export/import macros
#ifdef _WIN32
    #ifdef AUDIO_ANALYZER_BRIDGE_EXPORTS
        #define AUDIO_ANALYZER_BRIDGE_API __declspec(dllexport)
    #else
        #define AUDIO_ANALYZER_BRIDGE_API __declspec(dllimport)
    #endif
#else
    #ifdef AUDIO_ANALYZER_BRIDGE_EXPORTS
        #define AUDIO_ANALYZER_BRIDGE_API __attribute__((visibility("default")))
    #else
        #define AUDIO_ANALYZER_BRIDGE_API
    #endif
#endif

/**
 * @file AudioAnalyzerBridge.h
 * @brief C API for BPM and beat analysis, FFT processing for audio files.
 */

extern "C"
{
    /**
     * @brief Initialize the Audio Analyzer Bridge and all global components.
     *
     * @return true on successful initialization, false on failure.
     */
    AUDIO_ANALYZER_BRIDGE_API bool InitializeAudioAnalyzerBridge();

    /**
     * @brief Load full-quality audio data from a file (for playback, waveform, or full analysis).
     *
     * @param filename Path to the audio file (wide string).
     * @param outData Pointer to output buffer (allocated inside function).
     * @param length Pointer to receive number of samples.
     * @param sampleRate Pointer to receive sample rate in Hz.
     * @return true on success, false on failure.
     */
    AUDIO_ANALYZER_BRIDGE_API bool LoadAudioFull(const wchar_t *filename, float **outData, unsigned int *length, unsigned int *sampleRate);

    /**
     * @brief Analyze the BPM of an audio file.
     *
     * @param filename Path to the audio file (wide string).
     * @return int Estimated BPM (0 if analysis fails).
     */
    AUDIO_ANALYZER_BRIDGE_API int AnalyzeFileBPM(const wchar_t *filename);

    

    /**
     * @brief Analyze full track for all beat positions.
     *
     * @param filename Path to the audio file (wide string).
     * @param beatPositions Pointer to receive allocated beat positions array.
     * @param numBeats Pointer to receive number of beats found.
     * @param sampleRate Pointer to receive sample rate.
     * @return true on success, false on error.
     */
    AUDIO_ANALYZER_BRIDGE_API bool AnalyzeFullTrackBeats(const wchar_t *filename, int **beatPositions, int *numBeats, unsigned int *sampleRate);

    /**
     * @brief Free memory allocated by AnalyzeFullTrackBeats.
     *
     * @param beatPositions Pointer to memory allocated by AnalyzeFullTrackBeats.
     */
    AUDIO_ANALYZER_BRIDGE_API void FreeBeatPositions(int *beatPositions);

    /**
     * @brief Change tempo of an audio file using FFT-based time stretching.
     *
     * @param inputFile Path to input audio file (wide string).
     * @param outputFile Path to output audio file (wide string).
     * @param stretchFactor Tempo stretch factor (1.0 = no change, 2.0 = double speed, 0.5 = half speed).
     * @param length Length in seconds to process (0 = entire file).
     * @return true on success, false on error.
     */
    AUDIO_ANALYZER_BRIDGE_API bool ChangeTempoWithFFT(const wchar_t *inputFile, const wchar_t *outputFile, float stretchFactor, float length);

    /**
     * @brief Clean up and free all resources used by the Audio Analyzer.
     */
    AUDIO_ANALYZER_BRIDGE_API void CleanupAudioAnalyzer();

    /**
     * @brief Get a Hanning window of specified size for signal processing.
     *
     * @param size Size of the window (must be > 0).
     * @param outWindow Pointer to output buffer (caller allocated, must be at least 'size' elements).
     * @return true on success, false on error.
     */
    AUDIO_ANALYZER_BRIDGE_API bool GetHanningWindow(unsigned int size, float *outWindow);

    /**
     * @brief Perform FFT on audio data and return magnitude spectrum directly.
     *
     * @param audioData Input audio samples.
     * @param length Number of samples (must be power of 2).
     * @param magnitudes Output magnitude spectrum (caller allocated, must be at least 'length/2+1' elements).
     * @return true on success, false on error.
     */
    AUDIO_ANALYZER_BRIDGE_API bool PerformFFTWithMagnitudes(const float *audioData, unsigned int length, float *magnitudes);

    /**
     * @brief Process spectrogram data for optimal visual display.
     *
     * @param spectrogramData Input spectrogram data (width * height elements).
     * @param width Width of the spectrogram.
     * @param height Height of the spectrogram.
     * @param processedData Output processed spectrogram data (caller allocated, must be at least 'width * height' elements).
     * @param dynamicRangeDb Dynamic range in dB (default: 60.0f).
     * @param gamma Gamma correction value (default: 0.7f).
     * @return true on success, false on error.
     */
    AUDIO_ANALYZER_BRIDGE_API bool ProcessSpectrogram(
        const float *spectrogramData,
        unsigned int width,
        unsigned int height,
        float *processedData,
        float dynamicRangeDb = 60.0f,
        float gamma = 0.7f);
}