#pragma once

#include <string>
#include <vector>
#include <stdexcept>

// Platform-specific includes
#ifdef _WIN32
    #include <windows.h>
#else
    #include <codecvt>
#endif

/**
 * @brief Class for loading audio files (WAV, MP3, FLAC) and converting to mono float data.
 */
class LoadAudioFunction
{
public:
    /**
     * @brief Construct a new LoadAudioFunction object.
     */
    LoadAudioFunction();

    /**
     * @brief Destroy the LoadAudioFunction object.
     */
    ~LoadAudioFunction();

    /**
     * @brief Load audio data from a file (WAV, MP3, FLAC) and optionally downsample for BPM analysis.
     *
     * @param filename Path to the audio file (wide string).
     * @param sampleRate Reference to receive the sample rate in Hz.
     * @param maxSeconds Maximum number of seconds to load (for preview/analysis, default 30.0).
     * @return std::vector<float> Loaded audio data (mono, float samples).
     * @throws std::runtime_error on file or decoding errors.
     */
    std::vector<float> loadAudio(const std::wstring &filename, unsigned int &sampleRate, const float maxSeconds = 30.0f);

    /**
     * @brief Load audio data from a file (WAV, MP3, FLAC) for tempo change processing (full quality, no downsampling).
     *
     * @param filename Path to the audio file (wide string).
     * @param sampleRate Reference to receive the sample rate in Hz.
     * @param length Length of the audio to load (in seconds, 0 for full file).
     * @return std::vector<float> Loaded audio data (mono, float samples).
     * @throws std::runtime_error on file or decoding errors.
     */
    std::vector<float> loadAudioAtOriginalRate(const std::wstring &filename, unsigned int &sampleRate, const float length);

private:
    /**
     * @brief Convert a UTF-16 wide string to a UTF-8 encoded std::string.
     *
     * @param wstr Input wide string (UTF-16).
     * @return std::string UTF-8 encoded string.
     */
    std::string wstring_to_string(const std::wstring &wstr);

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
    std::vector<float> decodeToMono(const std::wstring &filename, unsigned int &originalRate, float maxSeconds);
};
