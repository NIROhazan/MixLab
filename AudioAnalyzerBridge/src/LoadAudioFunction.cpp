#include "LoadAudioFunction.h"
#include <stdexcept>
#include <string>
#include <vector>
#include <iostream>

// Platform-specific includes
#ifdef _WIN32
    #include <windows.h>
#else
    #include <codecvt>
    #include <locale>
#endif

#define MINIMP3_IMPLEMENTATION
#include "minimp3_ex.h"
#define DR_FLAC_IMPLEMENTATION
#include "dr_flac.h"
#define DR_WAV_IMPLEMENTATION
#include "dr_wav.h"

/**
 * @brief Default constructor for LoadAudioFunction.
 */
LoadAudioFunction::LoadAudioFunction()
{
}

/**
 * @brief Destructor for LoadAudioFunction.
 */
LoadAudioFunction::~LoadAudioFunction()
{
}

/**
 * @brief Converts a UTF-16 wide string to a UTF-8 encoded std::string.
 *
 * @param wstr The input wide string.
 * @return The converted UTF-8 string.
 */
std::string LoadAudioFunction::wstring_to_string(const std::wstring &wstr)
{
    if (wstr.empty())
        return {};

#ifdef _WIN32
    // Windows implementation using WideCharToMultiByte
    int size = WideCharToMultiByte(CP_UTF8, 0, wstr.data(), -1, NULL, 0, NULL, NULL);
    std::string str(size - 1, 0);
    WideCharToMultiByte(CP_UTF8, 0, wstr.data(), -1, &str[0], size, NULL, NULL);
    return str;
#else
    // Linux/Unix implementation using codecvt
    std::wstring_convert<std::codecvt_utf8<wchar_t>> converter;
    return converter.to_bytes(wstr);
#endif
}

/**
 * @brief Decode an audio file (WAV/MP3/FLAC) to mono float data at the original sample rate.
 *
 * If maxSeconds > 0, limits the decoded frames to at most maxSeconds of audio.
 * If maxSeconds <= 0, decodes the full file.
 *
 * @param filename Path to the audio file (wide string).
 * @param originalRate Reference to receive the original sample rate of the file.
 * @param maxSeconds Maximum seconds to decode (<= 0 means full file).
 * @return std::vector<float> Mono float samples at the original sample rate.
 * @throws std::runtime_error on failure to load or decode audio.
*/
std::vector<float> LoadAudioFunction::decodeToMono(const std::wstring &filename, unsigned int &originalRate, float maxSeconds)
{
    std::vector<float> audio;
    originalRate = 0;

    if (filename.find(L".wav") != std::wstring::npos)
    {
        drwav wav;
#ifdef _WIN32
        if (!drwav_init_file_w(&wav, filename.c_str(), NULL))
#else
        const std::string file = wstring_to_string(filename);
        if (!drwav_init_file(&wav, file.c_str(), NULL))
#endif
            throw std::runtime_error("Failed to open WAV file");

        originalRate = wav.sampleRate;
        const size_t totalFrames = static_cast<size_t>(wav.totalPCMFrameCount);
        const size_t maxFrames = (maxSeconds > 0.0f) ? static_cast<size_t>(originalRate * maxSeconds) : totalFrames;
        const size_t framesToRead = std::min<size_t>(maxFrames, totalFrames);

        if (wav.channels == 1)
        {
            audio.resize(framesToRead);
            if (drwav_read_pcm_frames_f32(&wav, framesToRead, audio.data()) != framesToRead)
            {
                drwav_uninit(&wav);
                throw std::runtime_error("Failed to read WAV data");
            }
        }
        else
        {
            const size_t CHUNK_SIZE = 16384;
            std::vector<float> chunk(CHUNK_SIZE * wav.channels);
            audio.resize(framesToRead);

            size_t framesRead = 0;
            while (framesRead < framesToRead)
            {
                const size_t framesToProcess = std::min<size_t>(CHUNK_SIZE, framesToRead - framesRead);
                const size_t actualFramesRead = drwav_read_pcm_frames_f32(&wav, framesToProcess, chunk.data());
                if (actualFramesRead == 0)
                    break;

                const float scale = 1.0f / wav.channels;
                for (size_t i = 0; i < actualFramesRead; i++)
                {
                    float sum = 0.0f;
                    for (unsigned int ch = 0; ch < wav.channels; ch++)
                        sum += chunk[i * wav.channels + ch];
                    audio[framesRead + i] = sum * scale;
                }
                framesRead += actualFramesRead;
            }
        }

        drwav_uninit(&wav);
    }
    else if (filename.find(L".mp3") != std::wstring::npos)
    {
#ifdef _WIN32
        FILE *file_ptr = _wfsopen(filename.c_str(), L"rb", _SH_DENYNO);
        if (!file_ptr)
        {
            throw std::runtime_error("Failed to open MP3 file with _wfsopen");
        }

        fseek(file_ptr, 0, SEEK_END);
        long file_size = ftell(file_ptr);
        fseek(file_ptr, 0, SEEK_SET);

        std::vector<unsigned char> file_buffer(file_size);
        if (fread(file_buffer.data(), 1, file_size, file_ptr) != static_cast<size_t>(file_size))
        {
            fclose(file_ptr);
            throw std::runtime_error("Failed to read MP3 file into buffer");
        }
        fclose(file_ptr);

        mp3dec_t mp3d;
        mp3dec_file_info_t info;
        mp3dec_init(&mp3d);

        if (mp3dec_load_buf(&mp3d, file_buffer.data(), file_buffer.size(), &info, NULL, NULL) != 0)
        {
            throw std::runtime_error("Failed to load MP3 from buffer");
        }
#else
        const std::string file = wstring_to_string(filename);
        mp3dec_t mp3d;
        mp3dec_file_info_t info;
        mp3dec_init(&mp3d);

        if (mp3dec_load(&mp3d, file.c_str(), &info, NULL, NULL) != 0)
        {
            throw std::runtime_error("Failed to load MP3 file");
        }
#endif
        originalRate = info.hz;
        const size_t totalFrames = static_cast<size_t>(info.samples / info.channels);
        const size_t maxFrames = (maxSeconds > 0.0f) ? static_cast<size_t>(originalRate * maxSeconds) : totalFrames;
        const size_t framesToRead = std::min<size_t>(maxFrames, totalFrames);

        if (framesToRead == 0 || info.buffer == nullptr)
        {
            free(info.buffer);
            throw std::runtime_error("Invalid MP3 data");
        }

        audio.resize(framesToRead);
        const float scale = 1.0f / (32768.0f * info.channels);
        for (size_t i = 0; i < framesToRead; i++)
        {
            float sum = 0.0f;
            for (int ch = 0; ch < info.channels; ch++)
                sum += info.buffer[i * info.channels + ch];
            audio[i] = sum * scale;
        }

        free(info.buffer);
    }
    else if (filename.find(L".flac") != std::wstring::npos)
    {
#ifdef _WIN32
        drflac *pFlac = drflac_open_file_w(filename.c_str(), NULL);
#else
        const std::string file = wstring_to_string(filename);
        drflac *pFlac = drflac_open_file(file.c_str(), NULL);
#endif
        if (!pFlac)
            throw std::runtime_error("Failed to open FLAC file");

        originalRate = pFlac->sampleRate;
        const size_t totalFrames = static_cast<size_t>(pFlac->totalPCMFrameCount);
        const size_t maxFrames = (maxSeconds > 0.0f) ? static_cast<size_t>(originalRate * maxSeconds) : totalFrames;
        const size_t framesToRead = std::min<size_t>(maxFrames, totalFrames);

        if (pFlac->channels == 1)
        {
            audio.resize(framesToRead);
            if (drflac_read_pcm_frames_f32(pFlac, framesToRead, audio.data()) != framesToRead)
            {
                drflac_close(pFlac);
                throw std::runtime_error("Failed to read FLAC data");
            }
        }
        else
        {
            const size_t CHUNK_SIZE = 16384;
            std::vector<float> chunk(CHUNK_SIZE * pFlac->channels);
            audio.resize(framesToRead);

            size_t framesRead = 0;
            while (framesRead < framesToRead)
            {
                const size_t framesToProcess = std::min<size_t>(CHUNK_SIZE, framesToRead - framesRead);
                const size_t actualFramesRead = drflac_read_pcm_frames_f32(pFlac, framesToProcess, chunk.data());
                if (actualFramesRead == 0)
                    break;

                const float scale = 1.0f / pFlac->channels;
                for (size_t i = 0; i < actualFramesRead; i++)
                {
                    float sum = 0.0f;
                    for (unsigned int ch = 0; ch < pFlac->channels; ch++)
                        sum += chunk[i * pFlac->channels + ch];
                    audio[framesRead + i] = sum * scale;
                }
                framesRead += actualFramesRead;
            }
        }

        drflac_close(pFlac);
    }
    else
    {
        throw std::runtime_error("Unsupported file format. Use WAV, MP3, or FLAC files.");
    }

    if (audio.empty() || originalRate == 0)
        throw std::runtime_error("No valid audio data was loaded");

    return audio;
}

/**
 * @brief Loads audio data from a file (WAV, MP3, or FLAC) and downsamples for BPM analysis.
 *
 * Loads up to maxSeconds of audio, converts to mono, and downsamples to a target rate for optimal BPM analysis.
 *
 * @param filename   The input file path (wide string).
 * @param sampleRate Reference to store the output sample rate.
 * @param maxSeconds Maximum seconds of audio to load.
 * @return A vector of mono, normalized float audio samples.
 * @throws std::runtime_error on failure to load or decode audio.
 */
std::vector<float> LoadAudioFunction::loadAudio(const std::wstring &filename, unsigned int &sampleRate, const float maxSeconds)
{
    std::vector<float> audio;
    unsigned int originalRate = 0;
    const size_t TARGET_RATE = 22050; // Optimal for BPM analysis

    try
    {
        audio = decodeToMono(filename, originalRate, maxSeconds);

        if (originalRate > TARGET_RATE)
        {
            const int factor = static_cast<int>(originalRate / TARGET_RATE);
            if (factor > 1)
            {
                std::vector<float> downsampled(audio.size() / static_cast<size_t>(factor));
                for (size_t i = 0; i < downsampled.size(); i++)
                {
                    float sum = 0.0f;
                    for (int j = 0; j < factor; j++)
                        sum += audio[i * static_cast<size_t>(factor) + static_cast<size_t>(j)];
                    downsampled[i] = sum / static_cast<float>(factor);
                }

                sampleRate = originalRate / static_cast<unsigned int>(factor);
                return downsampled;
            }
        }

        sampleRate = originalRate;
        return audio;
    }
    catch (const std::exception &e)
    {
        std::cout << "Error loading audio file: " << e.what() << std::endl;
        throw; // Re-throw the exception after logging
    }
}

/**
 * @brief Loads full-quality audio data from a file (WAV, MP3, or FLAC) for tempo change or waveform display.
 *
 * Loads the entire file, converts to mono, and preserves the original sample rate.
 *
 * @param filename   The input file path (wide string).
 * @param sampleRate Reference to store the output sample rate.
 * @param length     The length of audio to load (in seconds, ignored for full file).
 * @return A vector of mono, normalized float audio samples.
 * @throws std::runtime_error on failure to load or decode audio.
 */
std::vector<float> LoadAudioFunction::loadAudioAtOriginalRate(const std::wstring &filename, unsigned int &sampleRate, const float length)
{
    std::vector<float> audio;
    unsigned int originalRate = 0;

    try
    {
        audio = decodeToMono(filename, originalRate, length);
        sampleRate = originalRate;
        return audio;
    }
    catch (const std::exception &e)
    {
        std::cout << "Error loading audio file: " << e.what() << std::endl;
        throw;
    }
}