import ctypes
import os
import sys
import numpy as np
from ctypes import c_float, POINTER, Structure, c_uint
import logging
from cache_manager import AudioCacheManager

# Set up logging (consider configuring this globally in the main app later)
logging.basicConfig(level=logging.INFO) # Use INFO level for less verbose default output
logger = logging.getLogger(__name__)

# Keep structure definition as it matches the native library's expected output
class AudioData(Structure):
    _fields_ = [
        ("data", POINTER(c_float)),
        ("length", c_uint),
        ("sample_rate", c_uint)
    ]

# Audio analyzer bridge class that interfaces with the C++ library
class AudioAnalyzerBridge: 
    def __init__(self, library_path: str = None, cache_manager: AudioCacheManager = None):
        """
        Initialize the AudioAnalyzerBridge instance, load the library, set up function signatures, and initialize the analyzer.

        Args:
            library_path (str, optional): Path to the AudioAnalyzer library. If None, auto-detect based on platform.
            cache_manager (AudioCacheManager, optional): Cache manager for persistent storage.
        """
        self.native_lib = None # Initialize native library attribute
        self._bpm_cache = {}  # Add BPM cache (in-memory fallback)
        self.cache_manager = cache_manager or AudioCacheManager()  # Use provided cache manager or create new one
        
        # Auto-detect library path if not provided
        if library_path is None:
            library_path = self._get_default_library_path()
        
        try:
            if not os.path.exists(library_path):
                logger.error(f"Audio Analyzer library not found at specified path: {library_path}")
                return 
                
            self.native_lib = ctypes.CDLL(library_path)
            logger.info(f"Successfully loaded Audio Analyzer library from {library_path}")
            
            # Initialize function signatures
            self._init_function_signatures()
            
            # Initialize the analyzer via the library
            if not self.native_lib.InitializeAudioAnalyzerBridge():
                 logger.error("Failed to initialize Audio Analyzer Bridge via library function.")
                 self.native_lib = None # Mark library as unusable
                 return

            logger.info("Audio Analyzer Bridge initialized successfully via library.")
            
        except Exception as e:
            logger.error(f"Failed to load or initialize BPM analyzer library: {e}", exc_info=True)
            self.native_lib = None # Ensure native library is None on error
    
    def _get_default_library_path(self) -> str:
        """
        Get the default library path based on the current platform.
        
        Returns:
            str: Path to the appropriate library file.
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        if sys.platform == 'win32':
            return os.path.join(script_dir, "AudioAnalyzerBridge.dll")
        elif sys.platform == 'darwin':  # macOS
            return os.path.join(script_dir, "libAudioAnalyzerBridge.dylib")
        else:  # Linux and other Unix
            return os.path.join(script_dir, "libAudioAnalyzerBridge.so")
    
    def is_available(self) -> bool:
        """
        Check if the analyzer loaded and initialized correctly.

        Returns:
            bool: True if the native library is loaded and initialized, False otherwise.
        """
        return self.native_lib is not None

    def _init_function_signatures(self):
        """
        Initialize the function signatures for the native library.

        Sets up the argument and return types for all native library functions used by this class.
        Handles missing functions and logs warnings or errors.
        """
        if not self.native_lib: return # Don't setup if native library failed to load
        
        try:
            # Initialize function
            self.native_lib.InitializeAudioAnalyzerBridge.restype = ctypes.c_bool
            self.native_lib.InitializeAudioAnalyzerBridge.argtypes = []
            
            
            # BPM analysis function (core function)
            self.native_lib.AnalyzeFileBPM.restype = ctypes.c_int # Returns BPM as int
            self.native_lib.AnalyzeFileBPM.argtypes = [ctypes.c_wchar_p] # Takes filename
            
            # Full track beat analysis function
            self.native_lib.AnalyzeFullTrackBeats.restype = ctypes.c_bool
            self.native_lib.AnalyzeFullTrackBeats.argtypes = [
                ctypes.c_wchar_p,                           # filename
                ctypes.POINTER(ctypes.POINTER(ctypes.c_int)), # beatPositions (output)
                ctypes.POINTER(ctypes.c_int),               # numBeats (output)
                ctypes.POINTER(ctypes.c_uint)               # sampleRate (output)
            ]
            
            # Memory cleanup function for beat positions
            self.native_lib.FreeBeatPositions.restype = None
            self.native_lib.FreeBeatPositions.argtypes = [ctypes.POINTER(ctypes.c_int)]
            
            # Note: We always use PerformFFTWithMagnitudes now
            
           
            # Tempo change function (for pitch/tempo control)
            self.native_lib.ChangeTempoWithFFT.restype = ctypes.c_bool
            self.native_lib.ChangeTempoWithFFT.argtypes = [
                ctypes.c_wchar_p,  # inputFile
                ctypes.c_wchar_p,  # outputFile
                ctypes.c_float,    # stretchFactor 
                ctypes.c_float     # length (in seconds?) - Check DLL docs
            ]

            # Hanning window function
            self.native_lib.GetHanningWindow.restype = ctypes.c_bool
            self.native_lib.GetHanningWindow.argtypes = [
                ctypes.c_uint,                   # size
                ctypes.POINTER(ctypes.c_float)   # outWindow
            ]

            # FFT with magnitudes function
            self.native_lib.PerformFFTWithMagnitudes.restype = ctypes.c_bool
            self.native_lib.PerformFFTWithMagnitudes.argtypes = [
                ctypes.POINTER(ctypes.c_float),  # audioData (input)
                ctypes.c_uint,                   # length
                ctypes.POINTER(ctypes.c_float)   # magnitudes (output)
            ]

            # Spectrogram processing function
            self.native_lib.ProcessSpectrogram.restype = ctypes.c_bool
            self.native_lib.ProcessSpectrogram.argtypes = [
                ctypes.POINTER(ctypes.c_float),  # spectrogramData (input)
                ctypes.c_uint,                   # width
                ctypes.c_uint,                   # height
                ctypes.POINTER(ctypes.c_float),  # processedData (output)
                ctypes.c_float,                  # dynamicRangeDb
                ctypes.c_float                   # gamma
            ]

            # Full-quality loader
            self.native_lib.LoadAudioFull.restype = ctypes.c_bool
            self.native_lib.LoadAudioFull.argtypes = [
                ctypes.c_wchar_p,
                ctypes.POINTER(ctypes.POINTER(ctypes.c_float)),
                ctypes.POINTER(ctypes.c_uint),
                ctypes.POINTER(ctypes.c_uint)
            ]     
            
            # Cleanup function
            self.native_lib.CleanupAudioAnalyzer.restype = None
            self.native_lib.CleanupAudioAnalyzer.argtypes = []
            
            logger.debug("Native library function signatures initialized.")
        except AttributeError as e:
             logger.error(f"Failed to set function signature: {e}. Check native library exports.", exc_info=True)
             self.native_lib = None # Mark as unavailable if signatures fail
        except Exception as e:
            logger.error(f"Unexpected error setting function signatures: {e}", exc_info=True)
            self.native_lib = None


    def analyze_file(self, file_path: str) -> tuple[int, list[int]]:
        """
        Analyze an audio file for BPM and (not any more) beat positions using the native library.

        Args:
            file_path (str): Path to the audio file.

        Returns:
            tuple[int, list[int]]: Tuple of (bpm, []).
        """
        if not self.is_available():
            logger.warning("Audio analyzer native library not available, cannot analyze.")
            return 0, []
            
        if not os.path.exists(file_path):
            logger.error(f"Audio file not found for analysis: {file_path}")
            return 0, []
        
        # Check persistent cache first (BPM only)
        cached_bpm, _ = self.cache_manager.get_bpm_data(file_path)
        if cached_bpm is not None and cached_bpm > 0:
            logger.debug(f"Using persistent cached BPM for {file_path}: BPM={cached_bpm}")
            # Update in-memory cache (no beats stored here)
            self._bpm_cache[file_path] = (cached_bpm, [])
            return cached_bpm, []
        
        # Check in-memory cache as fallback (BPM only)
        if file_path in self._bpm_cache:
            logger.debug(f"Using in-memory cached BPM for {file_path}")
            return self._bpm_cache[file_path]
        
        logger.debug(f"Analyzing file: {file_path}")
        try:
            # Call native library BPM analysis
            bpm = self.native_lib.AnalyzeFileBPM(file_path)
            if bpm <= 0:
                logger.warning(f"BPM analysis failed or returned invalid BPM ({bpm})")
                self._bpm_cache[file_path] = (0, [])
                return 0, []

            # Cache and return result
            result = (bpm, [])
            
            # Save to persistent cache
            try:
                # Save BPM only; beat positions will be cached by full-track analysis
                self.cache_manager.cache_bpm_data(file_path, bpm, [], full_track=False)
                logger.debug(f"Saved BPM (without beats) to persistent cache for {file_path}")
            except Exception as e:
                logger.warning(f"Failed to save to persistent cache: {e}")
            
            # Also save to in-memory cache for quick access
            self._bpm_cache[file_path] = result
            logger.info(f"Analysis complete: BPM={bpm}")
            return result
            
        except Exception as e:
            logger.error(f"Error during analysis: {e}", exc_info=True)
            # Don't cache failed results to persistent storage, only mark in memory to avoid retry loops
            self._bpm_cache[file_path] = (0, [])
            return 0, []


    
            
    

    def get_hanning_window(self, size: int) -> np.ndarray | None:
        """
        Get a Hanning window of specified size from the C++ implementation.
        
        Args:
            size (int): Size of the window (must be > 0).
            
        Returns:
            np.ndarray | None: Hanning window as numpy array, or None on error.
        """
        if not self.is_available() or size <= 0:
            return None
            
        try:
            # Allocate output buffer
            window_buffer = (ctypes.c_float * size)()
            
            # Call the native function
            success = self.native_lib.GetHanningWindow(size, window_buffer)
            
            if success:
                # Convert to numpy array
                window_array = np.array(window_buffer, dtype=np.float32)
                return window_array
            else:
                logger.error(f"Failed to generate Hanning window of size {size}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting Hanning window: {e}", exc_info=True)
            return None

    def perform_fft_with_magnitudes(self, audio_chunk: np.ndarray) -> np.ndarray | None:
        """
        Perform FFT on an audio chunk and return magnitude spectrum directly using C++.
        
        Args:
            audio_chunk (np.ndarray): Numpy array (float32) of audio samples.
            
        Returns:
            np.ndarray | None: Numpy array of FFT magnitudes, or None on failure.
        """
        if not self.is_available(): 
            return None
        
        try:
            if audio_chunk is None or len(audio_chunk) == 0:
                logger.warning("No audio data provided for FFT")
                return None

            # Ensure data is float32 and contiguous for ctypes
            if audio_chunk.dtype != np.float32:
                audio_chunk = audio_chunk.astype(np.float32)
            if not audio_chunk.flags['C_CONTIGUOUS']:
                audio_chunk = np.ascontiguousarray(audio_chunk)
            
            # Get data pointer and length for FFT call
            data_length = len(audio_chunk)
            audio_ptr = audio_chunk.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            
            # Calculate output size (first half + 1 for real input)
            magnitudes_size = data_length // 2 + 1
            magnitudes_buffer = (ctypes.c_float * magnitudes_size)()
            
            # Call native library function
            success = self.native_lib.PerformFFTWithMagnitudes(
                audio_ptr,
                ctypes.c_uint(data_length),
                ctypes.cast(magnitudes_buffer, ctypes.POINTER(ctypes.c_float))
            )
            
            if not success:
                logger.warning("FFT with magnitudes processing failed in native library")
                return None
                
            # Convert C array to numpy array
            magnitudes = np.ctypeslib.as_array(magnitudes_buffer)
            return magnitudes.copy()  # Return a copy to avoid memory issues
            
        except Exception as e:
            logger.error(f"Error in perform_fft_with_magnitudes: {e}", exc_info=True)
            return None

    def process_spectrogram(self, spectrogram_data: np.ndarray, dynamic_range_db: float = 60.0, gamma: float = 0.7) -> np.ndarray | None:
        """
        Process spectrogram data for optimal visual display using C++.
        
        Args:
            spectrogram_data (np.ndarray): Input spectrogram data (2D array).
            dynamic_range_db (float): Dynamic range in dB (default: 60.0).
            gamma (float): Gamma correction value (default: 0.7).
            
        Returns:
            np.ndarray | None: Processed spectrogram data as uint8 array, or None on failure.
        """
        if not self.is_available(): 
            return None
        
        try:
            if spectrogram_data is None or spectrogram_data.size == 0:
                logger.warning("No spectrogram data provided for processing")
                return None

            # Ensure data is float32 and contiguous
            if spectrogram_data.dtype != np.float32:
                spectrogram_data = spectrogram_data.astype(np.float32)
            if not spectrogram_data.flags['C_CONTIGUOUS']:
                spectrogram_data = np.ascontiguousarray(spectrogram_data)

            # Get dimensions
            height, width = spectrogram_data.shape
            total_elements = width * height
            
            # Get data pointer
            data_ptr = spectrogram_data.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            
            # Create output buffer
            processed_buffer = (ctypes.c_float * total_elements)()
            
            # Call native library function
            success = self.native_lib.ProcessSpectrogram(
                data_ptr,
                ctypes.c_uint(width),
                ctypes.c_uint(height),
                ctypes.cast(processed_buffer, ctypes.POINTER(ctypes.c_float)),
                ctypes.c_float(dynamic_range_db),
                ctypes.c_float(gamma)
            )
            
            if not success:
                logger.warning("Spectrogram processing failed in native library")
                return None
                
            # Convert C array to numpy array, reshape to original dimensions, and convert to uint8
            processed = np.ctypeslib.as_array(processed_buffer)
            processed = processed.reshape((height, width))  # Reshape back to 2D
            return processed.astype(np.uint8).copy()  # Return a copy to avoid memory issues
            
        except Exception as e:
            logger.error(f"Error in process_spectrogram: {e}", exc_info=True)
            return None

    def change_tempo(self, input_file: str, output_file: str, stretch_factor: float, length_seconds: float) -> bool:
        """
        Change audio tempo using the native library's FFT time stretching.

        Args:
            input_file (str): Path to the input audio file.
            output_file (str): Path to save the processed audio file.
            stretch_factor (float): Factor to stretch audio (>1 slows down, <1 speeds up).
            length_seconds (float): Original length of audio in seconds (check if native library requires this).

        Returns:
            bool: True if successful, False otherwise.
        """
        if not self.is_available(): 
            logger.error("BPM Analyzer native library not available, cannot change tempo.")
            return False
            
        try:
            if not os.path.exists(input_file):
                logger.error(f"Tempo change failed: Input file not found: {input_file}")
                return False
                
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            success = self.native_lib.ChangeTempoWithFFT(
                input_file,
                output_file,
                ctypes.c_float(stretch_factor),
                ctypes.c_float(length_seconds)
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Error changing tempo: {e}")
            return False

    def cleanup(self):
        """
        Clean up resources.
        """
        if self.is_available() and hasattr(self.native_lib, 'CleanupAudioAnalyzer'):
            try:
                logger.info("Cleaning up Audio analyzer via native library.")
                self.native_lib.CleanupAudioAnalyzer()
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
        self.native_lib = None
        
    def __del__(self):
        """
        Ensure cleanup is called when the object is garbage collected.

        Destructor to ensure resources are released when the object is deleted.
        """
        self.cleanup()

    def load_audio_for_playback(self, file_path: str) -> tuple[np.ndarray, int]:
        """
        Load audio at full quality for playback and waveform display.

        Args:
            file_path (str): Path to the audio file.

        Returns:
            tuple[np.ndarray, int]: Tuple of (audio_data, sample_rate). Returns (None, 0) on failure.
        """
        if not self.is_available():
            return None, 0
        
        # Check persistent cache first
        cached_waveform, cached_sample_rate = self.cache_manager.get_waveform_data(file_path)
        if cached_waveform is not None and cached_sample_rate is not None:
            logger.debug(f"Using cached waveform data for {file_path}: {len(cached_waveform)} samples at {cached_sample_rate}Hz")
            return cached_waveform, cached_sample_rate
            
        try:
            audio_data_ptr = ctypes.POINTER(ctypes.c_float)()
            length = ctypes.c_uint()
            sample_rate = ctypes.c_uint()
            
            # New name in native library: LoadAudioFull
            success = self.native_lib.LoadAudioFull(
                file_path,
                ctypes.byref(audio_data_ptr),
                ctypes.byref(length),
                ctypes.byref(sample_rate)
            )
            
            if not success:
                logger.error(f"LoadAudioFull failed for {file_path}")
                return None, 0
                
            if audio_data_ptr and length.value > 0:
                array_size = length.value
                audio_data = np.ctypeslib.as_array(audio_data_ptr, shape=(array_size,)).copy()
                
                # Cache the waveform data for future use
                try:
                    self.cache_manager.cache_waveform_data(file_path, audio_data, sample_rate.value)
                    logger.debug(f"Cached waveform data for {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to cache waveform data: {e}")
                
                return audio_data, sample_rate.value
            else:
                logger.error(f"LoadAudioFull returned invalid data for {file_path}")
                return None, 0
                
        except Exception as e:
            logger.error(f"Error in load_audio_for_playback: {e}", exc_info=True)
            return None, 0



    def get_full_track_beat_positions_ms(self, file_path: str) -> list[int]:
        """
        Get beat positions for the entire track.

        Args:
            file_path (str): Path to the audio file.

        Returns:
            list[int]: List of beat positions in milliseconds for the full track.
        """
        if not self.is_available():
            logger.warning("BPM Analyzer native library not available, cannot analyze full track beats.")
            return []
            
        if not os.path.exists(file_path):
            logger.error(f"Audio file not found for full track analysis: {file_path}")
            return []
        
        # Prefer cached full-track beats if already available
        cached_entry = None
        if hasattr(self.cache_manager, 'get_bpm_cache_entry'):
            cached_entry = self.cache_manager.get_bpm_cache_entry(file_path)
        if cached_entry and cached_entry.get("full_track") and cached_entry.get("beat_positions"):
            logger.debug(f"Using cached full-track beats for {file_path}: {len(cached_entry.get('beat_positions', []))} beats")
            return cached_entry.get("beat_positions", [])
        
        # Check in-memory cache dedicated for full-track beats as fallback
        full_track_cache_key = f"{file_path}_full_track"
        if hasattr(self, '_full_track_cache') and full_track_cache_key in self._full_track_cache:
            logger.debug(f"Using in-memory cached full track beats for {file_path}")
            return self._full_track_cache[full_track_cache_key]
        
        logger.debug(f"Analyzing full track beats for: {file_path}")
        try:
            # Prepare output parameters
            beat_positions_ptr = ctypes.POINTER(ctypes.c_int)()
            num_beats = ctypes.c_int()
            sample_rate = ctypes.c_uint()
            
            # Call the native library function
            success = self.native_lib.AnalyzeFullTrackBeats(
                file_path,
                ctypes.byref(beat_positions_ptr),
                ctypes.byref(num_beats),
                ctypes.byref(sample_rate)
            )
            
            if not success:
                logger.error(f"Full track beat analysis failed for {file_path}")
                return []
                
            if num_beats.value == 0:
                logger.info(f"No beats detected in full track: {file_path}")
                return []
                
            if not beat_positions_ptr:
                logger.error(f"Beat positions pointer is null for {file_path}")
                return []
            
            # Convert frame positions to milliseconds
            beat_positions_ms = []
            hop_size = 768  # Custom hop size for beat display precision
            
            for i in range(num_beats.value):
                frame_pos = beat_positions_ptr[i]
                ms_pos = int((frame_pos * hop_size * 1000) / sample_rate.value)
                beat_positions_ms.append(ms_pos)
            
            # Free the memory allocated by the native library
            try:
                if hasattr(self.native_lib, 'FreeBeatPositions') and beat_positions_ptr:
                    self.native_lib.FreeBeatPositions(beat_positions_ptr)
            except Exception as e:
                logger.warning(f"Failed to free beat positions memory: {e}")
            
            # Cache the result in persistent cache (this will also update the BPM cache)
            try:
                # Get the BPM from the regular cache or analyze if needed
                bpm = 0
                bpm_cached_value, _ = self.cache_manager.get_bpm_data(file_path)
                if bpm_cached_value is not None:
                    bpm = bpm_cached_value
                elif file_path in self._bpm_cache:
                    bpm, _ = self._bpm_cache[file_path]
                else:
                    # Analyze to get BPM
                    bpm, _ = self.analyze_file(file_path)
                
                # Cache both BPM and full track beats, mark as full_track
                self.cache_manager.cache_bpm_data(file_path, bpm, beat_positions_ms, full_track=True)
                logger.debug(f"Saved full track beats to persistent cache for {file_path}")
            except Exception as e:
                logger.warning(f"Failed to save full track beats to persistent cache: {e}")
            
            # Also save to in-memory cache for quick access
            if not hasattr(self, '_full_track_cache'):
                self._full_track_cache = {}
            self._full_track_cache[full_track_cache_key] = beat_positions_ms
            
            logger.info(f"Full track analysis complete: {len(beat_positions_ms)} beats detected")
            return beat_positions_ms
            
        except Exception as e:
            logger.error(f"Error during full track beat analysis: {e}", exc_info=True)
            return [] 