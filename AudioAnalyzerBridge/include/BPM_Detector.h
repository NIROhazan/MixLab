#pragma once

#include <vector>


/**
 * @brief Class for detecting beats and estimating tempo (BPM) from audio data.
 */
class BPM_Detector
{
public:
    /**
     * @brief Construct a new BPM_Detector object.
     */
    BPM_Detector();

    /**
     * @brief Destroy the BPM_Detector object.
     */
    ~BPM_Detector();

    /**
     * @brief Multi-resolution onset detection for precise beat tracking.
     *
     * Computes the onset strength envelope using spectral flux across multiple window sizes.
     * Applies adaptive median filtering for baseline removal.
     *
     * @param samples Input audio samples (mono, normalized float).
     * @param sampleRate Audio sample rate in Hz.
     * @return std::vector<float> Onset strength envelope (filtered, non-negative values).
     */
    std::vector<float> detectOnsets(const std::vector<float> &samples, const unsigned int sampleRate);

    /**
     * @brief Enhanced peak picking with adaptive thresholding.
     *
     * Finds peaks in the onset function using a moving average and standard deviation for adaptive thresholding.
     *
     * @param onsetFunction Onset strength envelope (output of detectOnsets).
     * @param thresholdFactor Multiplier for local standard deviation to set the threshold (default: 1.3).
     * @return std::vector<size_t> Indices of detected beat peaks.
     */
    std::vector<size_t> findBeats(const std::vector<float> &onsetFunction, float thresholdFactor = 1.3f);

    /**
     * @brief High-precision tempo estimation using multi-level analysis.
     *
     * Estimates the tempo (BPM) from detected beat positions using inter-beat intervals and a weighted histogram.
     *
     * @param beats Indices of detected beat peaks (output of findBeats).
     * @param sampleRate Audio sample rate in Hz.
     * @param hopSize Hop size used in onset detection (in samples).
     * @return int Estimated tempo in BPM (0 if unreliable or insufficient data).
     */
    int estimateTempo(const std::vector<size_t> &beats, unsigned int sampleRate, unsigned int hopSize);

private:
};

