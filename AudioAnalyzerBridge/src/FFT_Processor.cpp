#define NOMINMAX // Prevent Windows.h from defining min/max macros
#define _USE_MATH_DEFINES

#include "FFT_Processor.h"
#include <vector>
#include <complex>
#include <algorithm>
#include <cmath>

/**
 * @brief Default constructor for FFT_Processor.
 */
FFT_Processor::FFT_Processor()
{
}

/**
 * @brief Destructor for FFT_Processor.
 */
FFT_Processor::~FFT_Processor()
{
}

/**
 * @brief Performs an in-place Fast Fourier Transform (FFT) using the Cooley-Tukey algorithm.
 *
 * @param x Vector of complex numbers representing the input signal (size must be a power of 2).
 */
void FFT_Processor::FFT(std::vector<std::complex<float>> &x)
{
    const size_t N = x.size();
    if (N <= 1)
        return;

    // Ensure the input size is a power of 2
    if ((N & (N - 1)) != 0)
    {
        throw std::invalid_argument("FFT size must be a power of 2");
    }

    // Bit-reversal permutation (reorders input for efficient processing)
    size_t j = 0;
    for (size_t i = 1; i < N; i++)
    {
        size_t bit = N >> 1;
        while (j >= bit)
        {
            j -= bit;
            bit >>= 1;
        }
        j += bit;
        if (i < j)
        {
            std::swap(x[i], x[j]);
        }
    }

    // Precompute twiddle factors to avoid redundant calculations inside loops
    std::vector<std::complex<float>> twiddles(N / 2);
    for (size_t i = 0; i < N / 2; i++)
    {
        float angle = -2.0f * M_PI * i / N;
        twiddles[i] = std::complex<float>(std::cos(angle), std::sin(angle));
    }

    // Cooley-Tukey iterative FFT (radix-2 DIT)
    for (size_t len = 2; len <= N; len *= 2)
    {
        size_t half_len = len / 2;
        size_t step = N / len; // Precompute twiddle factor step

        for (size_t i = 0; i < N; i += len)
        {
            for (size_t j = 0; j < half_len; j++)
            {
                size_t index = j * step;
                std::complex<float> twiddle = twiddles[index];

                std::complex<float> temp = x[i + j + half_len] * twiddle;
                x[i + j + half_len] = x[i + j] - temp;
                x[i + j] += temp;
            }
        }
    }
}

/**
 * @brief Performs an in-place Inverse Fast Fourier Transform (IFFT) using the Cooley-Tukey algorithm.
 *
 * @param x Vector of complex numbers representing the frequency domain (size must be a power of 2).
 */
void FFT_Processor::IFFT(std::vector<std::complex<float>> &x)
{
    const size_t N = x.size();
    if (N <= 1)
        return;

    // Ensure the input size is a power of 2
    if ((N & (N - 1)) != 0)
    {
        throw std::invalid_argument("IFFT size must be a power of 2");
    }

    // Take complex conjugate before and after regular FFT to get IFFT
    for (auto &val : x)
    {
        val = std::conj(val);
    }

    // Use regular FFT
    FFT(x);

    // Take complex conjugate again and normalize
    float normFactor = 1.0f / static_cast<float>(N);
    for (auto &val : x)
    {
        val = std::conj(val) * normFactor;
    }
}

/**
 * @brief Creates a Hanning window for signal processing.
 *
 * @param size Size of the window.
 * @return std::vector<float> Vector containing the Hanning window coefficients.
 */
std::vector<float> FFT_Processor::hanningWindow(unsigned int size)
{
    std::vector<float> window(size);
    for (unsigned int i = 0; i < size; i++)
    {
        window[i] = 0.5f * (1.0f - std::cos(2.0f * M_PI * i / (size - 1)));
    }
    return window;
}

/**
 * @brief Applies a Hann window to the input buffer in-place.
 *
 * This function multiplies each element of the buffer by the Hann window function to reduce spectral leakage before FFT.
 *
 * @param buffer The input/output buffer to which the Hann window will be applied.
 */
void FFT_Processor::applyHannWindow(std::vector<float> &buffer)
{
    const size_t N = buffer.size();
    const float norm = static_cast<float>(2.0 * M_PI / (N - 1));

    for (int i = 0; i < static_cast<int>(N); i++)
    {
        buffer[i] *= 0.5f * (1.0f - std::cos(i * norm));
    }
}

/**
 * @brief Applies the phase vocoder algorithm to the spectrum for time stretching.
 *
 * @param spectrum Complex spectrum to be modified.
 * @param stretchFactor Factor by which to stretch the signal (>1 makes it longer/slower, <1 makes it shorter/faster).
 * @param previousPhase Optional vector of previous frame's phase values for phase coherence.
 * @param previousMagnitude Optional vector of previous frame's magnitude values for transient detection.
 * @param frameDelta Time difference between analysis frames.
 * @return std::vector<std::complex<float>> Modified complex spectrum.
 */
std::vector<std::complex<float>> FFT_Processor::applyPhaseVocoder(
    const std::vector<std::complex<float>> &spectrum,
    float stretchFactor,
    std::vector<float> &previousPhase,
    std::vector<float> &previousMagnitude,
    float frameDelta)
{
    const size_t N = spectrum.size();
    std::vector<std::complex<float>> modifiedSpectrum(N);

    const size_t numBins = N / 2 + 1;
    const float omega = 2.0f * M_PI / N;

    // Detect transients by comparing magnitude changes
    bool isTransient = false;
    float magnitudeRatio = 0.0f;
    for (size_t i = 1; i < numBins - 1; i++)
    {
        float currentMag = std::abs(spectrum[i]);
        if (previousMagnitude[i] > 0.0f)
        {
            float ratio = currentMag / previousMagnitude[i];
            magnitudeRatio += ratio;
            if (ratio > 3.0f) // Sudden magnitude increase indicates transient
            {
                isTransient = true;
                break;
            }
        }
    }

    // Process positive frequency bins
    for (size_t i = 0; i < numBins; i++)
    {
        float magnitude = std::abs(spectrum[i]);
        float phase = std::arg(spectrum[i]);

        float newPhase = phase;

        if (i > 0 && i < numBins - 1) // Skip DC and Nyquist
        {
            if (isTransient && magnitude > 0.01f)
            {
                // For transients, preserve original phase relationships
                newPhase = phase;
            }
            else
            {
                // Normal phase vocoder processing for steady-state sounds
                float expectedPhaseAdvance = omega * i * frameDelta;
                float phaseDiff = phase - previousPhase[i];

                // Unwrap phase difference
                phaseDiff = phaseDiff - 2.0f * M_PI * std::round(phaseDiff / (2.0f * M_PI));

                // Calculate instantaneous frequency
                float instFreq = expectedPhaseAdvance + phaseDiff / frameDelta;

                // Calculate new phase with time stretching
                newPhase = previousPhase[i] + instFreq * frameDelta * stretchFactor;
            }
        }
        else
        {
            // Keep DC and Nyquist real
            newPhase = 0.0f;
            magnitude = std::abs(spectrum[i]);
        }

        // Store result
        modifiedSpectrum[i] = std::polar(magnitude, newPhase);

        // Update tracking arrays
        previousPhase[i] = newPhase;
        previousMagnitude[i] = magnitude;
    }

    // Create conjugate symmetric spectrum for negative frequencies
    for (size_t i = 1; i < N / 2; i++)
    {
        modifiedSpectrum[N - i] = std::conj(modifiedSpectrum[i]);
    }

    // Ensure DC and Nyquist are real
    modifiedSpectrum[0] = std::complex<float>(modifiedSpectrum[0].real(), 0.0f);
    if (N % 2 == 0)
    {
        modifiedSpectrum[N / 2] = std::complex<float>(modifiedSpectrum[N / 2].real(), 0.0f);
    }

    return modifiedSpectrum;
}

/**
 * @brief Applies time stretching to an audio signal using the phase vocoder.
 *
 * @param input Input audio samples.
 * @param stretchFactor Factor to stretch time by (>1 makes it longer/slower, <1 makes it shorter/faster).
 * @param windowSize Size of the FFT window, must be a power of 2.
 * @return std::vector<float> Stretched audio signal.
 */
std::vector<float> FFT_Processor::timeStretch(
    const std::vector<float> &input,
    float stretchFactor,
    unsigned int windowSize)
{
    if (input.empty() || stretchFactor <= 0.0f)
    {
        return input;
    }

    // If the stretch factor is very close to 1.0, just return the original audio
    if (std::abs(stretchFactor - 1.0f) < 0.001f)
    {
        return input;
    }

    // Validate stretch factor range
    if (stretchFactor < 0.25f || stretchFactor > 4.0f)
    {
        return input;
    }

    // Use 4096 window size for better quality
    windowSize = 4096;

    // Use 75% overlap (hop size = window/4)
    const unsigned int analysisHop = windowSize / 4;
    const unsigned int synthesisHop = static_cast<unsigned int>(analysisHop * stretchFactor);

    // Create analysis and synthesis windows
    std::vector<float> analysisWindow = hanningWindow(windowSize);
    std::vector<float> synthesisWindow = hanningWindow(windowSize);

    // Proper normalization for WOLA (Weighted Overlap-Add)
    // Calculate the sum of squared window values at the analysis hop interval
    float analysisWindowSum = 0.0f;
    for (unsigned int i = 0; i < windowSize; i += analysisHop)
    {
        if (i < windowSize)
        {
            analysisWindowSum += analysisWindow[i] * analysisWindow[i];
        }
    }

    // Normalize analysis window for unity gain
    if (analysisWindowSum > 0.0f)
    {
        float analysisNorm = 1.0f / std::sqrt(analysisWindowSum);
        for (size_t i = 0; i < windowSize; i++)
        {
            analysisWindow[i] *= analysisNorm;
        }
    }

    // For synthesis window, we need to account for variable hop size
    // Use a more conservative normalization that preserves amplitude better
    float synthesisNorm = 1.0f;
    for (size_t i = 0; i < windowSize; i++)
    {
        synthesisWindow[i] *= synthesisNorm;
    }

    // Calculate output size
    size_t outputLength = static_cast<size_t>(input.size() * stretchFactor + windowSize);
    std::vector<float> output(outputLength, 0.0f);

    // Add padding to input
    std::vector<float> paddedInput(input.size() + windowSize * 2, 0.0f);
    std::copy(input.begin(), input.end(), paddedInput.begin() + windowSize);

    // Initialize phase tracking
    std::vector<float> previousPhase(windowSize / 2 + 1, 0.0f);
    std::vector<float> previousMagnitude(windowSize / 2 + 1, 0.0f);

    // Track overlap compensation
    std::vector<float> overlapCompensation(outputLength, 0.0f);

    // Process frames
    std::vector<std::complex<float>> frame(windowSize);
    size_t outputPos = 0;

    for (size_t pos = 0; pos + windowSize <= paddedInput.size(); pos += analysisHop)
    {
        // Analysis: apply window and FFT
        for (size_t i = 0; i < windowSize; i++)
        {
            frame[i] = std::complex<float>(paddedInput[pos + i] * analysisWindow[i], 0.0f);
        }

        FFT(frame);

        // Phase vocoder processing
        float frameDelta = static_cast<float>(analysisHop) / 44100.0f; // Assume 44.1kHz
        std::vector<std::complex<float>> processedFrame = applyPhaseVocoder(
            frame, stretchFactor, previousPhase, previousMagnitude, frameDelta);

        // Synthesis: IFFT and apply window
        IFFT(processedFrame);

        // Overlap-add with amplitude compensation
        if (outputPos + windowSize <= output.size())
        {
            for (size_t i = 0; i < windowSize; i++)
            {
                float windowedSample = processedFrame[i].real() * synthesisWindow[i];
                output[outputPos + i] += windowedSample;
                overlapCompensation[outputPos + i] += synthesisWindow[i] * synthesisWindow[i];
            }
        }

        outputPos += synthesisHop;
    }

    // Apply overlap compensation to maintain consistent amplitude
    for (size_t i = 0; i < output.size(); i++)
    {
        if (overlapCompensation[i] > 0.01f) // Avoid division by very small numbers
        {
            output[i] /= std::sqrt(overlapCompensation[i]);
        }
    }

    // Trim output to expected length
    size_t expectedLength = static_cast<size_t>(input.size() * stretchFactor);
    if (expectedLength < output.size())
    {
        output.resize(expectedLength);
    }

    // Calculate RMS of input and output for amplitude matching
    float inputRMS = 0.0f;
    float outputRMS = 0.0f;

    for (float sample : input)
    {
        inputRMS += sample * sample;
    }
    inputRMS = std::sqrt(inputRMS / input.size());

    for (float sample : output)
    {
        outputRMS += sample * sample;
    }
    outputRMS = std::sqrt(outputRMS / output.size());

    // Amplitude matching: preserve the RMS level of the original
    if (outputRMS > 0.0f && inputRMS > 0.0f)
    {
        float amplitudeCorrection = inputRMS / outputRMS;
        // Limit correction to prevent extreme amplification
        amplitudeCorrection = std::min(amplitudeCorrection, 3.0f);

        for (float &sample : output)
        {
            sample *= amplitudeCorrection;
        }
    }

    // Final safety clipping
    for (float &sample : output)
    {
        sample = std::max(-0.95f, std::min(0.95f, sample));
    }

    return output;
}
