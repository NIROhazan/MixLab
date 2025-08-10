#pragma once

#include <complex>
#include <vector>

/**
 * @class FFT_Processor
 * @brief Provides FFT, IFFT, and time-stretching functionalities for audio processing.
 */
class FFT_Processor
{
public:
    /**
     * @brief Constructs a new FFT_Processor object.
     */
    FFT_Processor();

    /**
     * @brief Destroys the FFT_Processor object.
     */
    ~FFT_Processor();

    /**
     * @brief Performs the Fast Fourier Transform (FFT) on the input vector.
     * @param x A reference to a vector of complex floats representing the input signal. The result is stored in-place.
     */
    void FFT(std::vector<std::complex<float>> &x);

    /**
     * @brief Performs the Inverse Fast Fourier Transform (IFFT) on the input vector.
     * @param x A reference to a vector of complex floats representing the frequency domain signal. The result is stored in-place.
     */
    void IFFT(std::vector<std::complex<float>> &x);

    /**
     * @brief Stretches the input audio signal in time without affecting its pitch.
     * @param input The input audio signal as a vector of floats.
     * @param stretchFactor The factor by which to stretch the signal (e.g., 2.0 doubles the length).
     * @param windowSize The size of the analysis window (default is 2048).
     * @return A vector of floats containing the time-stretched audio signal.
     */
    std::vector<float> timeStretch(const std::vector<float> &input, float stretchFactor, unsigned int windowSize = 2048);

    /**
     * @brief Generates a Hanning window of the specified size.
     * @param size The size of the window.
     * @return A vector of floats containing the Hanning window coefficients.
     */
    std::vector<float> hanningWindow(unsigned int size);

    /**
     * @brief Applies a Hann window to the input buffer in-place.
     * @param buffer The input/output buffer to which the Hann window will be applied.
     */
    void applyHannWindow(std::vector<float> &buffer);

private:
    /**
     * @brief Applies the phase vocoder algorithm to the given spectrum for time-stretching.
     * @param spectrum The input frequency spectrum as a vector of complex floats.
     * @param stretchFactor The factor by which to stretch the signal.
     * @param previousPhase A reference to a vector storing the previous phase values.
     * @param previousMagnitude A reference to a vector storing the previous magnitude values.
     * @param frameDelta The time difference between frames.
     * @return A vector of complex floats representing the processed spectrum.
     */
    std::vector<std::complex<float>> applyPhaseVocoder(
        const std::vector<std::complex<float>> &spectrum,
        float stretchFactor,
        std::vector<float> &previousPhase,
        std::vector<float> &previousMagnitude,
        float frameDelta);
};
