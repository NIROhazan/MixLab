#include "BPM_Detector.h"
#include <cmath>
#include <vector>
#include <complex>
#include <algorithm>
#include <unordered_map>
#include "FFT_Processor.h"


/**
 * @brief Default constructor for BPM_Detector.
 */
BPM_Detector::BPM_Detector()
{
}

/**
 * @brief Destructor for BPM_Detector.
 */
BPM_Detector::~BPM_Detector()
{
}

/**
 * @brief Detects onsets in an audio signal using multi-resolution spectral flux analysis.
 *
 * This function computes the onset strength envelope by analyzing the spectral flux at multiple window sizes, normalizing, and applying adaptive median filtering for baseline removal.
 *
 * @param samples    The input audio samples (mono, normalized float values).
 * @param sampleRate The sample rate of the audio signal in Hz.
 * @return A vector of onset strength values (one per analysis frame).
 */
std::vector<float> BPM_Detector::detectOnsets(const std::vector<float> &samples, const unsigned int sampleRate)
{
    FFT_Processor fftProcessor;
    // Multiple window sizes for frequency/time resolution trade-offs
    const size_t windowSizes[] = {1024, 2048};
    const size_t hopSize = 512; // Fixed hop size for all window sizes

    // Calculate number of frames
    const size_t numFrames = (samples.size() - windowSizes[0]) / hopSize + 1;
    std::vector<float> onsetStrength(numFrames, 0.0f);

    // Process each window size
    for (const size_t windowSize : windowSizes)
    {
        std::vector<float> spectralFlux(numFrames, 0.0f);
        std::vector<float> buffer(windowSize);
        std::vector<std::complex<float>> fftBuffer(windowSize);
        std::vector<float> prevMagnitudes(windowSize / 2 + 1, 0.0f);

        // Compute spectral flux for current window size
        for (size_t frame = 0; frame < numFrames; frame++)
        {
            // Fill buffer and apply window
            for (size_t i = 0; i < windowSize; i++)
            {
                const size_t sampleIdx = frame * hopSize + i;
                buffer[i] = (sampleIdx < samples.size()) ? samples[sampleIdx] : 0.0f;
            }
            fftProcessor.applyHannWindow(buffer);

            // Copy to FFT buffer
            for (size_t i = 0; i < windowSize; i++)
            {
                fftBuffer[i] = std::complex<float>(buffer[i], 0.0f);
            }

            // Perform FFT
            fftProcessor.FFT(fftBuffer);

            // Calculate magnitudes and spectral flux
            float flux = 0.0f;
            for (size_t i = 1; i <= windowSize / 2; i++)
            { // Skip DC component (the first one)
                // Use frequency weighting to emphasize rhythm-relevant bands (100Hz-8kHz)
                const float freq = static_cast<float>(i) * sampleRate / windowSize;
                const float freqWeight = (freq > 100 && freq < 8000) ? 1.0f : 0.5f;

                const float mag = std::abs(fftBuffer[i]);
                const float diff = mag - prevMagnitudes[i];

                // Only consider positive changes (onsets, not offsets)
                if (diff > 0)
                    flux += diff * freqWeight;

                prevMagnitudes[i] = mag;
            }

            spectralFlux[frame] = flux;
        }

        // Normalize and add to combined onset strength
        float maxFlux = *std::max_element(spectralFlux.begin(), spectralFlux.end());
        if (maxFlux > 0)
        {
            for (size_t i = 0; i < numFrames; i++)
            {
                onsetStrength[i] += spectralFlux[i] / maxFlux;
            }
        }
    }

    // Normalize the combined onset strength
    for (auto &val : onsetStrength)
    {
        val /= 2.0f; // Normalize by number of window sizes
    }

    // Apply adaptive median filtering for baseline removal
    const int medianSize = 11;
    std::vector<float> medianFiltered(onsetStrength.size());
    std::vector<float> window(medianSize);

    for (size_t i = 0; i < onsetStrength.size(); i++)
    {
        // Fill window
        for (int j = 0; j < medianSize; j++)
        {
            int idx = static_cast<int>(i) + j - medianSize / 2;
            if (idx < 0 || idx >= static_cast<int>(onsetStrength.size()))
                window[j] = 0;
            else
                window[j] = onsetStrength[idx];
        }

        // Find median
        std::nth_element(window.begin(), window.begin() + medianSize / 2, window.end());
        float median = window[medianSize / 2];

        // Subtract median to remove baseline, keep only positive values
        float diff = onsetStrength[i] - median;
        medianFiltered[i] = (diff > 0.0f) ? diff : 0.0f;
    }

    return medianFiltered;
}

/**
 * @brief Finds beat positions (peaks) in the onset function using adaptive thresholding and local maximum search.
 *
 * This function applies a moving average and standard deviation-based adaptive threshold, then picks peaks that exceed the threshold and are local maxima.
 *
 * @param onsetFunction   The onset strength envelope (output of detectOnsets).
 * @param thresholdFactor The factor to scale the standard deviation for adaptive thresholding.
 * @return A vector of indices corresponding to detected beat positions (in analysis frames).
 */
std::vector<size_t> BPM_Detector::findBeats(const std::vector<float> &onsetFunction, float thresholdFactor)
{
    std::vector<size_t> peaks;
    const size_t length = onsetFunction.size();

    // Calculate adaptive threshold
    std::vector<float> threshold(length);
    const int windowSize = 9; // Neighborhood window for peak detection

    // Moving average and standard deviation for thresholding
    const size_t statsWindow = 30;

    for (size_t i = 0; i < length; i++)
    {
        float sum = 0.0f, sumSq = 0.0f;
        int count = 0;

        // Calculate local statistics
        for (size_t j = (i > statsWindow / 2) ? (i - statsWindow / 2) : 0;
             j < (i + statsWindow / 2 < length ? i + statsWindow / 2 : length); j++)
        {
            sum += onsetFunction[j];
            sumSq += onsetFunction[j] * onsetFunction[j];
            count++;
        }

        const float mean = sum / count;
        const float variance = (sumSq / count) - (mean * mean);
        threshold[i] = mean + thresholdFactor * std::sqrt(variance);
    }

    // Find peaks
    for (size_t i = windowSize; i < length - windowSize; i++)
    {
        if (onsetFunction[i] <= threshold[i])
            continue;

        // Check if local maximum
        bool isPeak = true;
        for (int j = -windowSize; j <= windowSize; j++)
        {
            if (j == 0)
                continue;

            const int idx = static_cast<int>(i) + j;
            if (idx >= 0 && idx < static_cast<int>(length) && onsetFunction[idx] > onsetFunction[i])
            {
                isPeak = false;
                break;
            }
        }

        if (isPeak)
            peaks.push_back(i);
    }

    return peaks;
}

/**
 * @brief Estimates the tempo (BPM) from detected beat positions using inter-beat interval analysis and histogram voting.
 *
 * This function computes all inter-beat intervals, converts them to BPM, and builds a weighted histogram to find the most likely tempo, considering musically related tempos (double, half, triple, etc.).
 *
 * @param beats      The vector of detected beat positions (indices in analysis frames).
 * @param sampleRate The sample rate of the audio signal in Hz.
 * @param hopSize    The hop size (in samples) used during onset detection.
 * @return The estimated tempo in beats per minute (BPM), or 0 if estimation is unreliable.
 */
int BPM_Detector::estimateTempo(const std::vector<size_t> &beats, unsigned int sampleRate, unsigned int hopSize)
{
    if (beats.size() < 4)
        return 0; // Need at least 4 beats for reliable estimation

    // Convert beat positions to times in seconds
    std::vector<float> beatTimes;
    beatTimes.reserve(beats.size());

    for (size_t beat : beats)
    {
        beatTimes.push_back(static_cast<float>(beat * hopSize) / sampleRate);
    }

    // Calculate all inter-beat intervals (IBIs)
    std::vector<float> intervals;
    intervals.reserve(beatTimes.size() - 1);

    for (size_t i = 1; i < beatTimes.size(); i++)
    {
        float ibi = beatTimes[i] - beatTimes[i - 1];
        // Filter out unreasonable intervals
        if (ibi >= 0.2f && ibi <= 2.0f)
        {
            intervals.push_back(ibi);
        }
    }

    if (intervals.empty())
        return 0;

    // Compute tempo histogram with high resolution
    std::unordered_map<int, float> tempoHistogram;

    // Weight intervals by their position in the sequence (recent intervals have higher weight)
    float totalWeight = 0;
    for (size_t i = 0; i < intervals.size(); i++)
    {
        const float weight = 0.5f + 0.5f * (static_cast<float>(i) / intervals.size());
        totalWeight += weight;

        // Convert interval to BPM and consider multiple interpretations
        const float primaryBPM = 60.0f / intervals[i];

        // Create weighted votes for this interval and related tempos
        const std::vector<std::pair<float, float>> tempos = {
            {primaryBPM, 1.0f},        // Primary tempo
            {primaryBPM * 2.0f, 0.9f}, // Double tempo (slightly lower weight)
            {primaryBPM / 2.0f, 0.8f}, // Half tempo (lower weight)
            {primaryBPM * 3.0f, 0.5f}, // Triple tempo (much lower weight)
            {primaryBPM / 3.0f, 0.5f}  // Third tempo (much lower weight)
        };

        // Add weighted votes to histogram with 0.5 BPM resolution
        for (const auto &tempo : tempos)
        {
            if (tempo.first >= 50.0f && tempo.first <= 220.0f)
            {
                // Use fine-grained BPM resolution (0.5 BPM)
                const int bpmKey = static_cast<int>(tempo.first * 2.0f);
                tempoHistogram[bpmKey] += weight * tempo.second;
            }
        }
    }

    // Find the strongest peak in the histogram
    int bestBPMKey = 0;
    float maxScore = 0;

    for (const auto &entry : tempoHistogram)
    {
        if (entry.second > maxScore)
        {
            maxScore = entry.second;
            bestBPMKey = entry.first;
        }
    }

    // Check nearby values to refine the estimate
    for (int offset = -3; offset <= 3; offset++)
    {
        const int nearbyKey = bestBPMKey + offset;
        if (tempoHistogram.count(nearbyKey) && tempoHistogram[nearbyKey] > 0.92f * maxScore)
        {
            // If a nearby tempo is almost as strong, average them for greater precision
            bestBPMKey = static_cast<int>((bestBPMKey * maxScore + nearbyKey * tempoHistogram[nearbyKey]) /
                                          (maxScore + tempoHistogram[nearbyKey]));
            break;
        }
    }

    // Convert from histogram key to actual BPM (accounting for 0.5 BPM resolution)
    float exactBPM = bestBPMKey / 2.0f;

    // Validate tempo is in reasonable range and musical
    if (exactBPM < 60.0f)
        exactBPM *= 2.0f;
    else if (exactBPM > 180.0f)
        exactBPM /= 2.0f;

    return static_cast<int>(std::round(exactBPM));
}
