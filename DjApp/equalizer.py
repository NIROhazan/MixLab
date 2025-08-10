import numpy as np
from scipy import signal
import traceback

class ThreeBandEQ:
    """
    A 3-band equalizer with real-time frequency band filtering.
    
    This equalizer provides:
    - Bass: Low-pass filter (0-250 Hz)
    - Mid: Band-pass filter (250-4000 Hz)  
    - Treble: High-pass filter (4000+ Hz)
    
    Pure-Python implementation that relies solely on NumPy and SciPy for the
    digital signal processing.
    """
    
    def __init__(self, sample_rate: int = 44100, audio_analyzer=None):
        """Create a 3-band equalizer.
        
        Args:
            sample_rate (int): Audio sample rate in Hz. Defaults to 44100.
            audio_analyzer: AudioAnalyzerBridge instance for using C++ hann function.
        """
        # Audio sample rate (Hz)
        self.sample_rate = sample_rate
        
        # Store audio analyzer for hann window generation
        self.audio_analyzer = audio_analyzer
        
        # Frequency band definitions
        self.bass_freq = 250    # Hz - Bass cutoff
        self.mid_freq_low = 250    # Hz - Mid low cutoff
        self.mid_freq_high = 4000  # Hz - Mid high cutoff  
        self.treble_freq = 4000    # Hz - Treble cutoff
        
        # Current sample rate is already stored in ``self.sample_rate`` above
        
        # Store previous gain values for smooth transitions
        self._prev_gains = {
            'bass': 1.0,
            'mid': 1.0, 
            'treble': 1.0
        }
        
        # Current gains (used for processing)
        self._current_gains = {
            'bass': 1.0,
            'mid': 1.0,
            'treble': 1.0
        }
        
        # Overlap for crossfading (to prevent clicking)
        self.overlap = 128
        self.prev_block = None
        
        # Initialise filter coefficients
        self._update_scipy_filters()

        # Informative log
        print(f"ThreeBandEQ initialised (sample_rate={self.sample_rate} Hz, pure-Python mode)")
    
    def _update_scipy_filters(self):
        """Update scipy filter coefficients for fallback processing"""
        try:
            # Low-pass filter for bass (0-250 Hz)
            self.bass_b, self.bass_a = signal.butter(4, self.bass_freq, btype='lowpass', fs=self.sample_rate)
            
            # Band-pass filter for mids (250-4000 Hz)
            self.mid_b, self.mid_a = signal.butter(4, [self.mid_freq_low, self.mid_freq_high], 
                                                 btype='bandpass', fs=self.sample_rate)
            
            # High-pass filter for treble (4000+ Hz)
            self.treble_b, self.treble_a = signal.butter(4, self.treble_freq, 
                                                        btype='highpass', fs=self.sample_rate)
            
            # Create crossfade window for smooth transitions
            if self.overlap > 0:
                # Use C++ hann function if available, otherwise fallback to numpy
                if self.audio_analyzer and hasattr(self.audio_analyzer, 'get_hanning_window'):
                    crossfade_win = self.audio_analyzer.get_hanning_window(self.overlap * 2)
                    if crossfade_win is None:
                        # Fallback to numpy implementation
                        crossfade_win = np.hanning(self.overlap * 2)
                else:
                    # Fallback to numpy implementation
                    crossfade_win = np.hanning(self.overlap * 2)
                
                self.crossfade_win = crossfade_win
                self.fade_in = self.crossfade_win[len(self.crossfade_win)//2:]
                self.fade_out = self.crossfade_win[:len(self.crossfade_win)//2]
            
            print(f"Scipy filters updated for sample rate: {self.sample_rate} Hz")
            
        except Exception as e:
            print(f"Error updating scipy filters: {e}")
    
    def set_sample_rate(self, sample_rate: int):
        """
        Set the sample rate and update filter coefficients.
        
        Args:
            sample_rate (int): Audio sample rate in Hz
        """
        if sample_rate != self.sample_rate:
            self.sample_rate = sample_rate
            self._update_scipy_filters()
    
    def process(self, audio_data: np.ndarray, sample_rate: int, 
                bass_gain: float, mid_gain: float, treble_gain: float) -> np.ndarray:
        """
        Process audio data with the 3-band equalizer using real-time frequency filtering.
        
        Args:
            audio_data (np.ndarray): Input audio as numpy array.
            sample_rate (int): Audio sample rate in Hz.
            bass_gain (float): Gain for bass frequencies (0.0-2.0).
            mid_gain (float): Gain for mid frequencies (0.0-2.0).
            treble_gain (float): Gain for treble frequencies (0.0-2.0).
        
        Returns:
            np.ndarray: Processed audio as numpy array.
        """
        try:
            # Validate input audio data
            if audio_data is None or len(audio_data) == 0:
                print("Empty audio data provided")
                return audio_data
            
            # Update sample rate if needed
            if sample_rate != self.sample_rate:
                self.set_sample_rate(sample_rate)
                
            # Validate gain values
            bass_gain = max(0.0, min(2.0, bass_gain))
            mid_gain = max(0.0, min(2.0, mid_gain))
            treble_gain = max(0.0, min(2.0, treble_gain))
            
            # Store current gains
            self._current_gains['bass'] = bass_gain
            self._current_gains['mid'] = mid_gain
            self._current_gains['treble'] = treble_gain
            
            print(f"EQ Processing: Bass: {bass_gain:.2f}, Mid: {mid_gain:.2f}, Treble: {treble_gain:.2f}")
            
            # Handle both mono and stereo audio
            if audio_data.ndim == 1:
                # Mono audio
                return self._process_mono_realtime(audio_data, bass_gain, mid_gain, treble_gain)
            elif audio_data.ndim == 2:
                # Stereo audio - process each channel separately
                left_channel = audio_data[:, 0]
                right_channel = audio_data[:, 1]
                
                left_processed = self._process_mono_realtime(left_channel, bass_gain, mid_gain, treble_gain)
                right_processed = self._process_mono_realtime(right_channel, bass_gain, mid_gain, treble_gain)
                
                # Combine back to stereo
                return np.column_stack((left_processed, right_processed))
            else:
                print(f"Unsupported audio format with {audio_data.ndim} dimensions")
                return audio_data
                
        except Exception as e:
            print(f"Error in equalizer processing: {e}")
            traceback.print_exc()
            return audio_data  # Return original on error
    
    def _process_mono_realtime(self, audio_data: np.ndarray, 
                              bass_gain: float, mid_gain: float, treble_gain: float) -> np.ndarray:
        """
        Process mono audio with real-time frequency band filtering.
        
        Args:
            audio_data (np.ndarray): Mono audio data.
            bass_gain (float): Gain for bass frequencies (0.0-2.0).
            mid_gain (float): Gain for mid frequencies (0.0-2.0).
            treble_gain (float): Gain for treble frequencies (0.0-2.0).
        
        Returns:
            np.ndarray: Processed mono audio as numpy array.
        """
        try:
            # Ensure audio data is in the correct ``float32`` format expected by
            # SciPy's filter routines.
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)

            # Directly apply the SciPy-based filters.
            return self._process_mono_scipy(audio_data, bass_gain, mid_gain, treble_gain)
            
        except Exception as e:
            print(f"Error in mono EQ processing: {e}")
            traceback.print_exc()
            return audio_data
    
    def _process_mono_scipy(self, audio_data: np.ndarray,
                           bass_gain: float, mid_gain: float, treble_gain: float) -> np.ndarray:
        """
        Process mono audio using scipy filters for real-time frequency band filtering.
        
        Args:
            audio_data (np.ndarray): Mono audio data.
            bass_gain (float): Gain for bass frequencies (0.0-2.0).
            mid_gain (float): Gain for mid frequencies (0.0-2.0).
            treble_gain (float): Gain for treble frequencies (0.0-2.0).
        
        Returns:
            np.ndarray: Processed mono audio as numpy array.
        """
        try:
            # Split frequencies into bands
            bass = signal.lfilter(self.bass_b, self.bass_a, audio_data)
            mid = signal.lfilter(self.mid_b, self.mid_a, audio_data)
            treble = signal.lfilter(self.treble_b, self.treble_a, audio_data)
            
            # Process each band with its gain and combine
            # When a gain is 0, that frequency band is effectively muted
            # When a gain is 1.0, that frequency band is unchanged
            # When a gain is > 1.0, that frequency band is amplified
            processed = np.zeros_like(audio_data)
            processed += bass * bass_gain  # Bass frequencies (0-250 Hz)
            processed += mid * mid_gain    # Mid frequencies (250-4000 Hz)
            processed += treble * treble_gain  # Treble frequencies (4000+ Hz)
            
            # Apply crossfading with previous block if available (for real-time use)
            if self.prev_block is not None and len(self.prev_block) >= self.overlap:
                try:
                    # Crossfade the overlapping region
                    overlap_region = np.zeros(min(self.overlap, len(processed)))
                    overlap_len = len(overlap_region)
                    
                    if overlap_len > 0:
                        prev_tail = self.prev_block[-overlap_len:]
                        current_head = processed[:overlap_len]
                        
                        fade_out_win = self.fade_out[:overlap_len] if hasattr(self, 'fade_out') else np.linspace(1, 0, overlap_len)
                        fade_in_win = self.fade_in[:overlap_len] if hasattr(self, 'fade_in') else np.linspace(0, 1, overlap_len)
                        
                        overlap_region = prev_tail * fade_out_win + current_head * fade_in_win
                        processed = np.concatenate([overlap_region, processed[overlap_len:]])
                        
                except Exception as crossfade_error:
                    print(f"Crossfade error (non-critical): {crossfade_error}")
            
            # Store the current block for next iteration's crossfading
            self.prev_block = processed.copy()
            
            # Soft-clip to safeguard against digital clipping while preserving
            # overall gain. This keeps values within the valid range without
            # scaling the entire signal back down (so boosts remain audible).
            processed = np.clip(processed, -1.0, 1.0)
            
            print("Python scipy EQ processing completed successfully")
            return processed.astype(np.float32)
            
        except Exception as e:
            print(f"Error in scipy EQ processing: {e}")
            traceback.print_exc()
            return audio_data
        
    def reset_transitions(self):
        """
        Reset the gain transition state to default values.
        
        Resets both the internal gain state and the EQ processor.
        """
        self._prev_gains = {
            'bass': 1.0,
            'mid': 1.0, 
            'treble': 1.0
        }
        self._current_gains = {
            'bass': 1.0,
            'mid': 1.0, 
            'treble': 1.0
        }
        
        # Reset crossfading state
        self.prev_block = None
        
        print("Equalizer transitions reset (pure-Python mode)")
