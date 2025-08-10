import time
import numpy as np
import logging
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QImage, qRgb
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRect, QObject, QRunnable, QThreadPool

logger = logging.getLogger(__name__) # Setup logger for this module

def compute_color_from_frequency_content(
    fft_magnitudes,
    sample_rate,
    low_freq_min_hz,
    low_mid_cutoff_hz,
    mid_high_cutoff_hz,
    low_freq_color,
    mid_freq_color,
    high_freq_color,
    invalid_color
):
    """Compute a QColor representing frequency content of the given FFT magnitudes.

    Returns invalid_color when input is invalid; returns a neutral gray when total
    energy is effectively zero.
    """
    # Validate input
    if not isinstance(fft_magnitudes, (list, np.ndarray)) or sample_rate == 0:
        return invalid_color
    if len(fft_magnitudes) == 0:
        return invalid_color

    # Ensure numpy array
    if isinstance(fft_magnitudes, list):
        fft_magnitudes = np.array(fft_magnitudes, dtype=np.float32)

    num_fft_bins = len(fft_magnitudes)
    actual_fft_n = (num_fft_bins - 1) * 2
    if actual_fft_n == 0:
        return invalid_color

    freq_per_bin = sample_rate / actual_fft_n

    low_energy = 0.0
    mid_energy = 0.0
    high_energy = 0.0
    for i, magnitude in enumerate(fft_magnitudes):
        freq = i * freq_per_bin
        energy = magnitude * magnitude
        if low_freq_min_hz <= freq < low_mid_cutoff_hz:
            low_energy += energy
        elif low_mid_cutoff_hz <= freq < mid_high_cutoff_hz:
            mid_energy += energy
        elif freq >= mid_high_cutoff_hz:
            high_energy += energy

    total_energy = low_energy + mid_energy + high_energy
    if total_energy < 1e-9:
        return QColor(50, 50, 50)

    r_comp = (
        (low_energy * low_freq_color.redF())
        + (mid_energy * mid_freq_color.redF())
        + (high_energy * high_freq_color.redF())
    ) / total_energy

    g_comp = (
        (low_energy * low_freq_color.greenF())
        + (mid_energy * mid_freq_color.greenF())
        + (high_energy * high_freq_color.greenF())
    ) / total_energy

    b_comp = (
        (low_energy * low_freq_color.blueF())
        + (mid_energy * mid_freq_color.blueF())
        + (high_energy * high_freq_color.blueF())
    ) / total_energy

    return QColor(int(r_comp * 255), int(g_comp * 255), int(b_comp * 255))

class FFTPreProcessor(QRunnable):
    """
    Worker for pre-calculating FFT data for the entire waveform.

    Args:
        signals (QObject): Signal object for thread communication.
        waveform_data (np.ndarray): Audio waveform data.
        sample_rate (int): Audio sample rate in Hz.
         audio_analyzer: Analyzer object with perform_fft_with_magnitudes method.
        fft_size (int): FFT window size.
    """
    def __init__(self, signals, waveform_data, sample_rate, audio_analyzer, fft_size):
        super().__init__()
        self.signals = signals
        self._waveform_data = waveform_data
        self._sample_rate = sample_rate
        self._audio_analyzer = audio_analyzer
        self._fft_size = fft_size
        
        # Define frequency bands directly here
        self.LOW_FREQ_MIN_HZ = 20
        self.LOW_MID_CUTOFF_HZ = 250
        self.MID_HIGH_CUTOFF_HZ = 4000
        self.LOW_FREQ_COLOR = QColor("red")
        self.MID_FREQ_COLOR = QColor("green")
        self.HIGH_FREQ_COLOR = QColor("blue")
        self.BG_COLOR = QColor(17, 17, 17)
        self.DEFAULT_SEGMENT_COLOR = QColor("gray")

    def _get_color_from_frequency_content(self, fft_magnitudes, sample_rate):
        """Delegate to shared helper for frequency-to-color mapping."""
        return compute_color_from_frequency_content(
            fft_magnitudes,
            sample_rate,
            self.LOW_FREQ_MIN_HZ,
            self.LOW_MID_CUTOFF_HZ,
            self.MID_HIGH_CUTOFF_HZ,
            self.LOW_FREQ_COLOR,
            self.MID_FREQ_COLOR,
            self.HIGH_FREQ_COLOR,
            self.BG_COLOR,
        )

    def run(self):
        """
        Pre-calculate FFT data for the entire waveform and emit results via signals.
        Emits:
            signals.finished (list): List of dicts with 'time_ms' and 'color'.
            signals.error (str): Error message if an exception occurs.
        """
        try:
            if self._waveform_data is None or len(self._waveform_data) == 0 or self._sample_rate == 0:
                try:
                    self.signals.finished.emit([])
                except RuntimeError:
                    # Signals object was deleted during app shutdown - ignore silently
                    pass
                return

            logger.info(f"Starting FFT pre-calculation for {len(self._waveform_data)} samples")
            
            # Create a Hanning window for FFT using C++ implementation
            if self._audio_analyzer and hasattr(self._audio_analyzer, 'get_hanning_window'):
                hanning_window = self._audio_analyzer.get_hanning_window(self._fft_size)
                if hanning_window is None:
                    # Fallback to Python implementation
                    hanning_window = np.hanning(self._fft_size)
            else:
                # Fallback to Python implementation
                hanning_window = np.hanning(self._fft_size)
            
            # Calculate how many FFT windows we need
            total_samples = len(self._waveform_data)
            stride = self._fft_size // 2  # 50% overlap for better resolution
            num_windows = (total_samples - self._fft_size) // stride + 1
            
            # Pre-allocate results array
            fft_results = []
            
            # Process each window
            for i in range(num_windows):
                if i % 1000 == 0:  # Log progress every 1000 windows
                    logger.debug(f"FFT pre-calculation progress: {i}/{num_windows} windows")
                
                start_sample = i * stride
                end_sample = start_sample + self._fft_size
                
                # Get audio chunk
                audio_chunk = self._waveform_data[start_sample:end_sample]
                
                # Apply window function
                windowed_chunk = audio_chunk * hanning_window
                
                # Calculate FFT magnitudes using analyzer
                fft_magnitudes = self._audio_analyzer.perform_fft_with_magnitudes(windowed_chunk)
                
                # Calculate color from frequency content
                if fft_magnitudes is not None:
                    color = self._get_color_from_frequency_content(fft_magnitudes, self._sample_rate)
                else:
                    color = self.DEFAULT_SEGMENT_COLOR
                
                # Store time position (in ms) and color
                time_ms = (start_sample / self._sample_rate) * 1000
                fft_results.append({
                    'time_ms': time_ms,
                    'color': color
                })
            
            logger.info(f"FFT pre-calculation complete: {len(fft_results)} windows processed")
            try:
                self.signals.finished.emit(fft_results)
            except RuntimeError as rte:
                logger.error(f"Error in FFTPreProcessor Signal failed: {rte}")
            
        except Exception as e:
            logger.error(f"Error in FFT pre-calculation: {e}", exc_info=True)
            try:
                self.signals.error.emit(str(e))
            except RuntimeError as rte:
                logger.error(f"Error in FFTPreProcessor: {rte}")

class WaveformRenderSignals(QObject):
    """
    Defines signals available from a rendering worker thread.
    Signals:
        finished (list): Carries the render_data.
        error (str): Error message.
    """
    finished = pyqtSignal(list) # Carries the render_data
    error = pyqtSignal(str)

class WaveformRenderWorker(QRunnable):
    """
    Worker thread for generating waveform render data.

    Args:
        signals (QObject): Signal object for thread communication.
        waveform_data (np.ndarray): Audio waveform data.
        sample_rate (int): Audio sample rate in Hz.
        duration (float): Duration of the audio in ms.
        position_ms (float): Current position in ms.
        view_window_ms (float): Window size in ms.
        playhead_position_ratio (float): Playhead position as a ratio.
        render_width (int): Width of the render area in pixels.
        render_height (int): Height of the render area in pixels.
        audio_analyzer: Analyzer object with perform_fft_with_magnitudes method.
        fft_size (int): FFT window size.
        fft_calc_interval_pixels (int): Interval for FFT calculation in pixels.
        pre_calculated_fft (list, optional): Pre-calculated FFT data.
    """
    def __init__(self, signals, waveform_data, sample_rate, duration,
                 position_ms, view_window_ms, playhead_position_ratio,
                 render_width, render_height, audio_analyzer, fft_size,
                 fft_calc_interval_pixels, pre_calculated_fft=None):
        super().__init__()
        self.signals = signals
        self._waveform_data = waveform_data
        self._sample_rate = sample_rate
        self._duration = duration
        self._position_ms = position_ms
        self._view_window_ms = view_window_ms
        self._playhead_position_ratio = playhead_position_ratio
        self._render_width = render_width
        self._render_height = render_height
        self._audio_analyzer = audio_analyzer
        self._fft_size = fft_size
        self._fft_calc_interval_pixels = fft_calc_interval_pixels
        self._pre_calculated_fft = pre_calculated_fft  # Use pre-calculated FFT data

        # Define frequency bands and colors directly here or pass them if they can change
        self.LOW_FREQ_MIN_HZ = 20
        self.LOW_MID_CUTOFF_HZ = 250
        self.MID_HIGH_CUTOFF_HZ = 4000
        self.LOW_FREQ_COLOR = QColor("red")
        self.MID_FREQ_COLOR = QColor("green")
        self.HIGH_FREQ_COLOR = QColor("blue")
        self.BG_COLOR = QColor(17, 17, 17) # Define fallback BG color
        self.DEFAULT_SEGMENT_COLOR = QColor("gray")

    def _get_color_from_frequency_content(self, fft_magnitudes, sample_rate):
        """Delegate to shared helper for frequency-to-color mapping."""
        return compute_color_from_frequency_content(
            fft_magnitudes,
            sample_rate,
            self.LOW_FREQ_MIN_HZ,
            self.LOW_MID_CUTOFF_HZ,
            self.MID_HIGH_CUTOFF_HZ,
            self.LOW_FREQ_COLOR,
            self.MID_FREQ_COLOR,
            self.HIGH_FREQ_COLOR,
            self.BG_COLOR,
        )

    def _find_nearest_fft_result(self, time_ms):
        """
        Find the nearest pre-calculated FFT result for a given time position.

        Args:
            time_ms (float): Time in milliseconds.
        Returns:
            QColor: Color from the nearest FFT result.
        """
        if not self._pre_calculated_fft:
            return self.DEFAULT_SEGMENT_COLOR
            
        # Binary search for the closest time position
        left = 0
        right = len(self._pre_calculated_fft) - 1
        
        while left <= right:
            mid = (left + right) // 2
            current = self._pre_calculated_fft[mid]['time_ms']
            
            if current < time_ms:
                left = mid + 1
            elif current > time_ms:
                right = mid - 1
            else:
                return self._pre_calculated_fft[mid]['color']
        
        # If we didn't find an exact match, return the closest one
        if right < 0:
            return self._pre_calculated_fft[0]['color']
        elif left >= len(self._pre_calculated_fft):
            return self._pre_calculated_fft[-1]['color']
        else:
            left_diff = abs(self._pre_calculated_fft[left]['time_ms'] - time_ms)
            right_diff = abs(self._pre_calculated_fft[right]['time_ms'] - time_ms)
            
            if left_diff < right_diff:
                return self._pre_calculated_fft[left]['color']
            else:
                return self._pre_calculated_fft[right]['color']

    def run(self):
        """
        Execute the rendering task and emit results via signals.
        Emits:
            signals.finished (list): List of render data dicts.
            signals.error (str): Error message if an exception occurs.
        """
        try:
            if self._waveform_data is None or len(self._waveform_data) == 0 or \
               self._duration == 0 or self._sample_rate == 0 or self._render_width == 0:
                try:
                    self.signals.finished.emit([])
                except RuntimeError:
                    # Signals object was deleted during app shutdown - ignore silently
                    pass
                return

            render_data = []
            center_y = self._render_height / 2
            scale_y = self._render_height / 2.5 
            samples_per_ms = self._sample_rate / 1000.0
            visible_start_ms = max(0, self._position_ms - (self._view_window_ms * self._playhead_position_ratio))
            
            view_samples_in_window = self._view_window_ms * samples_per_ms
            samples_per_pixel_view = max(1, int(view_samples_in_window / self._render_width))

            # Create a Hanning window for FFT using C++ implementation
            if self._audio_analyzer and hasattr(self._audio_analyzer, 'get_hanning_window'):
                hanning_window = self._audio_analyzer.get_hanning_window(self._fft_size)
                if hanning_window is None:
                    # Fallback to Python implementation
                    hanning_window = np.hanning(self._fft_size)
            else:
                # Fallback to Python implementation
                hanning_window = np.hanning(self._fft_size)
            last_calculated_color = self.DEFAULT_SEGMENT_COLOR

            for x_pixel in range(self._render_width):
                time_offset_in_window_ms = (x_pixel / self._render_width) * self._view_window_ms
                current_pixel_time_ms = visible_start_ms + time_offset_in_window_ms
                
                shape_chunk_start_sample = int(current_pixel_time_ms * samples_per_ms)
                shape_chunk_end_sample = shape_chunk_start_sample + samples_per_pixel_view
                shape_audio_chunk = self._waveform_data[
                    shape_chunk_start_sample : min(shape_chunk_end_sample, len(self._waveform_data))
                ]

                max_val, min_val = (0, 0) if len(shape_audio_chunk) == 0 else \
                                   (float(np.max(shape_audio_chunk)), float(np.min(shape_audio_chunk)))
                
                top_y = center_y - (max_val * scale_y)
                bottom_y = center_y - (min_val * scale_y)

                # Use pre-calculated FFT data if available
                if self._pre_calculated_fft:
                    current_segment_color = self._find_nearest_fft_result(current_pixel_time_ms)
                else:
            # Calculate FFT on-the-fly
                    current_segment_color = last_calculated_color # Default to last color
                    if self._audio_analyzer and (x_pixel % self._fft_calc_interval_pixels == 0):
                        fft_chunk_center_sample = int(current_pixel_time_ms * samples_per_ms)
                        fft_chunk_start = max(0, fft_chunk_center_sample - self._fft_size // 2)
                        fft_audio_chunk_for_fft = self._waveform_data[
                            fft_chunk_start : min(fft_chunk_start + self._fft_size, len(self._waveform_data))
                        ]

                        if len(fft_audio_chunk_for_fft) > 0:
                            actual_chunk_len = len(fft_audio_chunk_for_fft)
                            if actual_chunk_len < self._fft_size:
                                padded_chunk = np.zeros(self._fft_size, dtype=np.float32)
                                padded_chunk[:actual_chunk_len] = fft_audio_chunk_for_fft
                                windowed_chunk = padded_chunk * hanning_window # Use full Hanning window
                            else:
                                # Ensure chunk is exactly fft_size for direct multiplication
                                windowed_chunk = fft_audio_chunk_for_fft[:self._fft_size] * hanning_window 
                            
                            # Use FFT with magnitudes
                            fft_magnitudes = self._audio_analyzer.perform_fft_with_magnitudes(windowed_chunk)
                            if fft_magnitudes is not None:
                                current_segment_color = self._get_color_from_frequency_content(fft_magnitudes, self._sample_rate)
                                last_calculated_color = current_segment_color # Update last calculated color
                
                render_data.append({'x': x_pixel, 'top': top_y, 'bottom': bottom_y, 'color': current_segment_color})
            
            try:
                self.signals.finished.emit(render_data)
            except RuntimeError:
                # Signals object was deleted during app shutdown - ignore silently
                pass
        except Exception as e:
            logger.error(f"Error in WaveformRenderWorker: {e}", exc_info=True)
            try:
                self.signals.error.emit(str(e))
            except RuntimeError:
                # Signals object was deleted during app shutdown - ignore silently
                pass


class WaveformDisplay(QWidget):
    """
    A PyQt widget for displaying audio waveforms with advanced visualization features.
    Supports scrolling waveform display, beat markers, and frequency-colored waveform.
    """

    # Frequency band definitions
    LOW_FREQ_MIN_HZ = 20
    LOW_MID_CUTOFF_HZ = 250
    MID_HIGH_CUTOFF_HZ = 4000
    # Colors for bands
    LOW_FREQ_COLOR = QColor("red")
    MID_FREQ_COLOR = QColor("green")
    HIGH_FREQ_COLOR = QColor("blue")

    def __init__(self, parent=None):
        """
        Initialize the WaveformDisplay widget with default settings and visual configurations.

        Args:
            parent (QWidget, optional): Parent widget.
        """
        super().__init__(parent)
        self.setAutoFillBackground(False) # Prevent Qt from auto-filling background

        # Core data
        self._waveform_data = None
        self._sample_rate = None
        self._position = 0
        self._duration = 0
        self._beat_positions = []  # Store beat positions in milliseconds
        self._audio_analyzer = None
        self._pre_calculated_fft = None  # Store pre-calculated FFT data
        self._is_calculating_fft = False  # Flag to track FFT calculation status
        self._current_file_path = None  # Track current file path for FFT lookup
        
        # View settings
        self._view_window_ms = 10000  # Show 10 seconds of audio
        self._playhead_position = 0.3  # Playhead at 30% of width
        
        # Double buffering
        self._buffer = None
        self._buffer_valid = False
        self._last_width = 0
        self._last_height = 0
        
        # Performance settings
        self._last_update_time = 0
        self._min_update_interval = 16  # Target ~60 FPS for UI, actual render might be slower
        self._waveform_path = None
        self._cached_visible_beats = []
        
        # Amplitude colors
        self._amp_colors = [
            QColor(20, 20, 180, 100),    # Deep blue (lowest)
            QColor(30, 144, 255, 120),   # Dodger blue
            QColor(0, 200, 100, 140),    # Green
            QColor(243, 207, 44, 160),   # Yellow
            QColor(255, 140, 0, 180),    # Orange
            QColor(255, 50, 50, 200),    # Red
            QColor(255, 0, 128, 220)     # Magenta (highest)
        ]
        
        # Qt optimizations
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setMinimumHeight(150)  # Increased from 100 to 150
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)  # Changed to Expanding for vertical

        # Visual theme
        self.bg_color = QColor(17, 17, 17)
        self.waveform_color_future = QColor("#f3cf2c")
        self.waveform_color_past = QColor(243, 207, 44, 100)
        self.playhead_color = QColor("#f3cf2c")
        self.grid_color = QColor(243, 207, 44, 40)
        self.timeline_height = 20
        self.timeline_bg_color = QColor(17, 17, 17, 150)
        self.timeline_text_color = QColor("#f3cf2c")

        # FFT settings for native library FFT
        self.fft_size = 2048
        self.fft_calc_interval_pixels = 5 # Calculate FFT every 5 pixels

        # Remove hardcoded styles - let CSS handle theming
        self.setStyleSheet("")

        # Playback position tracking
        self.current_position = 0  # Current position in milliseconds
        self.duration = 0          # Total duration in milliseconds
        self.last_update_time = 0  # For throttling paint updates

        # Scrolling waveform settings
        self.scroll_mode = True  # Enable scrolling mode
        self.visible_range = 10000  # Visible time range in ms (10 seconds)
        self.update_timer = QTimer(self) # Set parent for timer
        self.update_timer.setInterval(16)  # Target ~60fps
        self.update_timer.timeout.connect(self.update) # Request repaint on timeout

        self.audio_data = None
        self.sample_rate = None
        self.playback_position = 0

        # Data for rendering the colored waveform
        self._waveform_render_data = [] # Stores {'x', 'top', 'bottom', 'color'}

        self.thread_pool = QThreadPool.globalInstance()
        self._is_rendering_waveform = False
        logger.info(f"WaveformDisplay Thread genutzt: Max Threads {self.thread_pool.maxThreadCount()}")

    def set_current_file_path_waveform(self, file_path):
        """
        Set the current file path.

        Args:
            file_path (str): Path to the current audio file.
        """
        self._current_file_path = file_path
    
    def _process_fft_data_to_colors(self, fft_data):
        """
        Process FFT magnitude data into colors for rendering.

        Args:
            fft_data (list): List of dicts with 'time_ms' and 'magnitudes'.
        Returns:
            list: List of dicts with 'time_ms' and 'color'.
        """
        if not fft_data:
            return None
            
        try:
            # Convert raw FFT data (magnitudes) to color information
            color_data = []
            for entry in fft_data:
                time_ms = entry['time_ms']
                magnitudes = entry['magnitudes']
                
                if magnitudes:
                    color = self._get_color_from_frequency_content(
                        magnitudes, self._sample_rate)
                    color_data.append({
                        'time_ms': time_ms,
                        'color': color
                    })
            
            logger.debug(f"Processed {len(color_data)} FFT entries to colors")
            return color_data
        except Exception as e:
            logger.error(f"Error processing FFT data to colors: {e}", exc_info=True)
            return None
    
    def _get_color_from_frequency_content(self, fft_magnitudes, sample_rate):
        """Delegate to shared helper for frequency-to-color mapping."""
        invalid_color = QColor(50, 50, 50)
        return compute_color_from_frequency_content(
            fft_magnitudes,
            sample_rate,
            self.LOW_FREQ_MIN_HZ,
            self.LOW_MID_CUTOFF_HZ,
            self.MID_HIGH_CUTOFF_HZ,
            self.LOW_FREQ_COLOR,
            self.MID_FREQ_COLOR,
            self.HIGH_FREQ_COLOR,
            invalid_color,
        )

    def set_audio_analyzer_with_cache(self, analyzer):
        """
        Set the Audio analyzer instance with cache manager setup.

        Args:
            analyzer: Audio analyzer instance.
        """
        self._audio_analyzer = analyzer
        # Get cache manager from analyzer if available
        if hasattr(analyzer, 'cache_manager'):
            self._cache_manager = analyzer.cache_manager
        # Potentially trigger a re-render if data already exists
        if self._waveform_data is not None:
             self._buffer_valid = False
             self.update()
            
    def set_waveform_data(self, data, sample_rate, beat_positions=None):
        """
        Set the waveform data and optionally beat positions.

        Args:
            data (np.ndarray): Audio waveform data.
            sample_rate (int): Audio sample rate in Hz.
            beat_positions (list, optional): List of beat positions in ms.
        """
        logger.debug(f"Setting waveform data: {len(data) if data is not None else 0} samples, Rate: {sample_rate}")
        
        # Check if we're setting the same data to avoid expensive recalculation
        data_unchanged = False
        if (self._waveform_data is not None and data is not None and 
            self._sample_rate == sample_rate and 
            len(self._waveform_data) == len(data)):
            # Quick check if data is the same (using numpy array comparison for efficiency)
            try:
                data_unchanged = np.array_equal(self._waveform_data, data)
                if data_unchanged:
                    logger.debug("Waveform data unchanged, skipping expensive recalculation")
                    # Only update beat positions if they changed
                    new_beat_positions = list(beat_positions) if beat_positions is not None else []
                    if new_beat_positions != self._beat_positions:
                        logger.debug("Beat positions changed, updating only beats")
                        self._beat_positions = new_beat_positions
                        self._buffer_valid = False
                        self.update()
                    return
            except Exception as e:
                logger.debug(f"Error comparing waveform data: {e}")
                data_unchanged = False
        
        # Data is different, proceed with full update
        self._waveform_data = data.copy() if data is not None else None # Work with a copy
        self._sample_rate = sample_rate
        self._beat_positions = list(beat_positions) if beat_positions is not None else []
        
        self._duration = (len(self._waveform_data) / self._sample_rate * 1000) if self._waveform_data is not None and self._sample_rate > 0 else 0
        
        # Check if we can use cached FFT data
        fft_data_found = False
        
        # First check if we already have FFT data for this file
        if self._current_file_path and hasattr(self, '_cached_file_for_fft') and self._cached_file_for_fft == self._current_file_path:
            # Same file, check if we have valid FFT data
            if self._pre_calculated_fft:
                logger.debug(f"Reusing existing FFT data for {self._current_file_path}")
                fft_data_found = True
        
        # If not found in memory, check persistent cache
        if (not fft_data_found and self._current_file_path and 
            hasattr(self, '_cache_manager') and self._cache_manager):
            try:
                cached_fft_data = self._cache_manager.get_fft_data(self._current_file_path)
                if cached_fft_data:
                    logger.info(f"Using cached FFT data from persistent storage for {self._current_file_path}")
                    # Check if this is waveform color data or traditional FFT magnitudes
                    if cached_fft_data and 'color_data' in cached_fft_data[0]:
                        # This is cached waveform color data, convert back to QColor format
                        color_data = []
                        for entry in cached_fft_data:
                            color_info = entry['color_data']
                            color = QColor(color_info['r'], color_info['g'], color_info['b'], color_info['a'])
                            color_data.append({
                                'time_ms': entry['time_ms'],
                                'color': color
                            })
                        self._pre_calculated_fft = color_data
                    else:
                        # Traditional FFT magnitudes, process to colors
                        self._pre_calculated_fft = self._process_fft_data_to_colors(cached_fft_data)
                    self._cached_file_for_fft = self._current_file_path
                    fft_data_found = True
            except Exception as e:
                logger.warning(f"Failed to load cached FFT data: {e}")
        
        if not fft_data_found:
            # Clear previous FFT data and calculate our own
            self._pre_calculated_fft = None
            self._buffer_valid = False
            # Start pre-calculating FFT data
            self._pre_calculate_all_fft()
                
        self._buffer_valid = False
        self.update()

    def _pre_calculate_all_fft(self):
        """
        Pre-calculate FFT data for the entire waveform in a background thread.
        """
        if self._waveform_data is None or self._sample_rate == 0 or self._audio_analyzer is None:
            logger.debug("Cannot pre-calculate FFT: missing data or analyzer")
            return
            
        if self._is_calculating_fft:
            logger.debug("FFT calculation already in progress")
            return
            
        self._is_calculating_fft = True
        logger.info("Starting FFT pre-calculation for entire waveform")
        
        signals = WaveformRenderSignals()
        worker = FFTPreProcessor(
            signals,
            self._waveform_data,
            self._sample_rate,
            self._audio_analyzer,
            self.fft_size
        )
        
        signals.finished.connect(self._on_fft_pre_calculation_finished)
        signals.error.connect(self._on_fft_pre_calculation_error)
        
        self.thread_pool.start(worker)

    def _on_fft_pre_calculation_finished(self, fft_results):
        """
        Handle completion of FFT pre-calculation.

        Args:
            fft_results (list): List of FFT calculation results.
        """
        logger.info(f"FFT pre-calculation complete: {len(fft_results)} results")
        self._pre_calculated_fft = fft_results
        self._is_calculating_fft = False
        
        # Cache the FFT results if we have a file path and cache manager
        if (self._current_file_path and hasattr(self, '_cache_manager') and 
            self._cache_manager and fft_results):
            try:
                # Store the color data directly in a special format
                fft_data_for_cache = []
                for entry in fft_results:
                    # Store color data in a special format for waveform cache
                    color = entry['color']
                    fft_data_for_cache.append({
                        'time_ms': entry['time_ms'],
                        'color_data': {
                            'r': color.red(),
                            'g': color.green(), 
                            'b': color.blue(),
                            'a': color.alpha()
                        }
                    })
                self._cache_manager.cache_fft_data(self._current_file_path, fft_data_for_cache)
                logger.debug(f"Cached waveform FFT color data for {self._current_file_path}")
            except Exception as e:
                logger.warning(f"Failed to cache FFT data: {e}")
        
        self._cached_file_for_fft = self._current_file_path
        self._buffer_valid = False
        self.update()

    def _on_fft_pre_calculation_error(self, error_message):
        """
        Handle errors in FFT pre-calculation.

        Args:
            error_message (str): Error message string.
        """
        logger.error(f"FFT pre-calculation error: {error_message}")
        self._is_calculating_fft = False
        self._pre_calculated_fft = None  # Clear any partial results
        # Fall back to on-the-fly calculation
        self._buffer_valid = False
        self.update()

    def _start_waveform_render_job(self, width, height):
        """
        Start a background job to render the waveform.

        Args:
            width (int): Width of the render area.
            height (int): Height of the render area.
        """
        if self._is_rendering_waveform:
            logger.debug("Waveform rendering already in progress. Skipping new job.")
            return 

        if self._waveform_data is None or self._sample_rate == 0 or width == 0 or height == 0:
            logger.debug("Not starting render job due to missing data or zero dimensions.")
            # If no data, ensure a clean state
            self._waveform_render_data = []
            self._cached_visible_beats = []
            self._buffer = QImage(max(1, width), max(1, height), QImage.Format.Format_ARGB32_Premultiplied)
            self._buffer.fill(self.bg_color)
            self._draw_placeholder_text(self._buffer) # Draw "load track first" if needed
            self._buffer_valid = True # Buffer has placeholder or is blank
            self.update()
            return

        logger.debug(f"Starting waveform render job for {width}x{height}")
        self._is_rendering_waveform = True
        
        signals = WaveformRenderSignals()
        # Pass copies or immutable data to worker where appropriate
        worker = WaveformRenderWorker(
            signals,
            self._waveform_data, # Already a copy from set_waveform_data
            self._sample_rate,
            self._duration,
            self._position, # Current position
            self._view_window_ms,
            self._playhead_position,
            width,
            height,
            self._audio_analyzer,
            self.fft_size,
            self.fft_calc_interval_pixels, # Pass the interval
            self._pre_calculated_fft  # Pass pre-calculated FFT data
        )
        signals.finished.connect(self._on_waveform_render_finished)
        signals.error.connect(self._on_waveform_render_error)
        self.thread_pool.start(worker)

    def _on_waveform_render_finished(self, render_data):
        """
        Handle completion of waveform rendering.

        Args:
            render_data (list): List of render data dicts.
        """
        logger.debug(f"Waveform render job finished. Received {len(render_data)} segments.")
        self._waveform_render_data = render_data
        self._is_rendering_waveform = False
        
        # Now that render data is ready, finalize the buffer content in the main thread
        self._finalize_buffer_content()
        self.update() # Trigger paintEvent

    def _on_waveform_render_error(self, error_message):
        """
        Handle errors in waveform rendering.

        Args:
            error_message (str): Error message string.
        """
        logger.error(f"Waveform rendering error: {error_message}")
        self._is_rendering_waveform = False
        # Potentially draw an error state on the waveform or log
        # For now, just ensure we try to redraw with placeholder if data is bad
        self._waveform_render_data = [] # Clear potentially partial data
        self._finalize_buffer_content() # Attempt to draw placeholder
        self.update()

    def _finalize_buffer_content(self):
        """
        Draws the waveform, beats, and time markers into self._buffer using current data.
        """
        width = self._last_width
        height = self._last_height

        if width == 0 or height == 0: return

        if self._buffer is None or self._buffer.width() != width or self._buffer.height() != height:
            self._buffer = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        
        self._buffer.fill(self.bg_color)
        painter = QPainter(self._buffer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        no_audio_data = self._waveform_data is None or self._waveform_data.size == 0
        no_render_data = not self._waveform_render_data

        if no_audio_data or no_render_data:
             if self._waveform_data is None:
                self._draw_placeholder_text(painter_or_image=painter)
        else:
            # Optimized drawing: set pen/brush once for runs of same color,
            # but draw individual 1px rects for shape fidelity.
            if len(self._waveform_render_data) > 0:
                i = 0
                while i < len(self._waveform_render_data):
                    current_segment = self._waveform_render_data[i]
                    current_color = current_segment['color']
                    
                    painter.setPen(current_color) # Set pen once for the color run
                    painter.setBrush(current_color) # Set brush once for the color run
                    
                    # Draw all contiguous segments of this color
                    j = i
                    while j < len(self._waveform_render_data) and \
                          self._waveform_render_data[j]['color'] == current_color and \
                          self._waveform_render_data[j]['x'] == current_segment['x'] + (j - i):
                        
                        segment_to_draw = self._waveform_render_data[j]
                        top_y = min(segment_to_draw['top'], segment_to_draw['bottom'])
                        bottom_y = max(segment_to_draw['top'], segment_to_draw['bottom'])
                        rect_height = bottom_y - top_y
                        if rect_height < 1: rect_height = 1
                        
                        painter.drawRect(segment_to_draw['x'], int(top_y), 1, int(rect_height))
                        j += 1
                    i = j # Move to the start of the next potential color run
        
        self._cached_visible_beats = self._update_visible_beats(width)
        if self._cached_visible_beats:
            beat_color = QColor(82, 183, 174, 200)
            painter.setPen(QPen(beat_color, 1.5))
            for x_pos, _ in self._cached_visible_beats:
                painter.drawLine(x_pos, 0, x_pos, height)
        
        if self._waveform_data is not None and self._waveform_data.size > 0:
            self._draw_time_markers(painter, width, height)
        
        painter.end()
        self._buffer_valid = True

    def _update_visible_beats(self, width):
        """
        Pre-calculate visible beat positions.

        Args:
            width (int): Width of the widget.
        Returns:
            list: List of tuples (x position, beat time in ms).
        """
        if not self._beat_positions or self._duration == 0 or width == 0:
            return []
            
        visible_start_ms = max(0, self._position - (self._view_window_ms * self._playhead_position))
        visible_end_ms = visible_start_ms + self._view_window_ms
        
        visible_beats_on_screen = []
        for beat_time_ms in self._beat_positions:
            if visible_start_ms <= beat_time_ms <= visible_end_ms:
                x = int(((beat_time_ms - visible_start_ms) / self._view_window_ms) * width)
                visible_beats_on_screen.append((x, beat_time_ms))
                
        return visible_beats_on_screen

    def _update_buffer(self):
        """
        Update the back buffer for double-buffered rendering.
        """
        current_width = self.width()
        current_height = self.height()

        # Skip if dimensions are invalid
        if current_width == 0 or current_height == 0:
            logger.debug("Update buffer: Widget not visible or not sized.")
            return

        # Check if we need to update the buffer
        needs_update = (
            not self._buffer_valid or
            current_width != self._last_width or
            current_height != self._last_height
        )

        if needs_update:
            self._last_width = current_width
            self._last_height = current_height

            # Only start a new render job if one isn't already in progress
            if not self._is_rendering_waveform:
                self._start_waveform_render_job(current_width, current_height)
            else:
                logger.debug("Skipping render job - already in progress")

    def _draw_placeholder_text(self, painter_or_image):
        """
        Draws 'Error loading tracks...' centered on the given QPainter or QImage. For error handling

        Args:
            painter_or_image (QPainter or QImage): Target for drawing text.
        """
        if isinstance(painter_or_image, QImage):
            painter = QPainter(painter_or_image)
        else: # Assume QPainter
            painter = painter_or_image

        font = QFont()
        font.setPointSize(16)
        painter.setFont(font)
        painter.setPen(self.timeline_text_color)
        if isinstance(painter_or_image, QImage):
             rect = painter_or_image.rect()
        else: # QPainter for a QWidget
             rect = painter.device().rect() if painter.device() else self.rect()

        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Error loading tracks...")
        if isinstance(painter_or_image, QImage): # End painter if we created it
            painter.end()


    def _draw_time_markers(self, painter, width, height):
        """
        Draw time markers on the waveform.

        Args:
            painter (QPainter): Painter object.
            width (int): Width of the widget.
            height (int): Height of the widget.
        """
        # Use theme-driven colors for time markers
        marker_color = self.timeline_text_color
        tick_color = QColor(marker_color.red(), marker_color.green(), marker_color.blue(), 150)
        painter.setPen(tick_color)
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
                
        visible_start_ms = max(0, self._position - (self._view_window_ms * self._playhead_position))
        
        for i in range(int(self._view_window_ms / 1000) + 2): 
            marker_offset_ms = (i * 1000) - (visible_start_ms % 1000)
            if marker_offset_ms > self._view_window_ms + 1000 : continue 

            time_ms_abs = visible_start_ms + marker_offset_ms
            if time_ms_abs < 0: continue

            x_pos = int((marker_offset_ms / self._view_window_ms) * width)
            
            if 0 <= x_pos <= width: 
                # Draw tick line with semi-transparent theme color
                painter.drawLine(x_pos, height - 15, x_pos, height - 10)
                minutes = int(time_ms_abs / 60000)
                seconds = int((time_ms_abs % 60000) / 1000)
                time_str = f"{minutes}:{seconds:02d}"
                text_width = painter.fontMetrics().boundingRect(time_str).width()
                # Draw label text with full-opacity theme color for readability
                painter.setPen(marker_color)
                painter.drawText(x_pos - text_width // 2, height - 2, time_str)

    def paintEvent(self, event):
        """
        Handle paint events for the widget.

        Args:
            event (QPaintEvent): Paint event object.
        """
        # Skip unnecessary updates if nothing has changed
        if event.rect().width() <= 5 and self._buffer is not None:
            # This is a playhead-only update
            painter = QPainter(self)
            
            # Draw the small section of buffer we need
            source_rect = event.rect()
            painter.drawImage(source_rect, self._buffer, source_rect)
            
            # Draw playhead
            if self._duration > 0:
                playhead_x = int(self.width() * self._playhead_position)
                if source_rect.contains(playhead_x, source_rect.height() // 2):
                    painter.setPen(QPen(self.playhead_color, 2))
                    painter.drawLine(playhead_x, 0, playhead_x, self.height())
            painter.end()
            return

        self._update_buffer()  # Ensures self._buffer is up-to-date

        painter = QPainter(self)

        if self._waveform_data is None or len(self._waveform_data) == 0:
            painter.fillRect(self.rect(), self.bg_color)
            font = QFont()
            font.setPointSize(16)
            painter.setFont(font)
            painter.setPen(self.timeline_text_color)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Load track first...")
            painter.end()
            return

        # Draw the buffer
        if self._buffer is not None:
            painter.drawImage(0, 0, self._buffer)

            # Draw the playhead line directly on top of the buffer content
            if self._duration > 0:
                playhead_x = int(self.width() * self._playhead_position)
                painter.setPen(QPen(self.playhead_color, 2))
                painter.drawLine(playhead_x, 0, playhead_x, self.height())

        painter.end()

    def set_position(self, position_ms, duration_ms, beat_positions=None):
        """
        Update playback position and optionally beat positions.

        Args:
            position_ms (float): Current playback position in ms.
            duration_ms (float): Total duration in ms.
            beat_positions (list, optional): List of beat positions in ms.
        """
        
        # First check if we should process this update at all
        current_time_ms = time.time() * 1000
        if current_time_ms - self._last_update_time < self._min_update_interval:
            return
        self._last_update_time = current_time_ms

        # Update duration if needed
        new_duration = (len(self._waveform_data) / self._sample_rate * 1000) if self._waveform_data is not None and self._sample_rate > 0 else 0
        if duration_ms != new_duration and new_duration > 0:
            self._duration = new_duration
            self._buffer_valid = False
        elif duration_ms != self._duration:
            self._duration = duration_ms
            self._buffer_valid = False

        # Check for significant position change
        position_change = abs(position_ms - self._position)
        significant_position_change = position_change > self._view_window_ms * 0.05  # 5% of view window

        # Handle beat positions
        beats_content_changed = False
        if beat_positions is not None:
            if len(beat_positions) != len(self._beat_positions) or \
               any(b1 != b2 for b1, b2 in zip(beat_positions, self._beat_positions)):
                beats_content_changed = True
                self._beat_positions = list(beat_positions)
        elif self._beat_positions:
            beats_content_changed = True
            self._beat_positions = []

        # Determine if we need to regenerate the buffer
        needs_buffer_update = (
            significant_position_change or
            beats_content_changed or
            not self._buffer_valid
        )

        # Update position
        self._position = position_ms

        if needs_buffer_update:
            logger.debug(f"Invalidating buffer - pos_change: {position_change}ms, significant: {significant_position_change}")
            self._buffer_valid = False
            self.update()
        else:
            # For minor position changes, only trigger a repaint for the playhead
            playhead_x = int(self.width() * self._playhead_position)
            # Update a narrow region around the playhead
            self.update(playhead_x - 2, 0, 5, self.height())  # 5px wide update region

class SpectrogramSignals(QObject):
    """
    Defines signals available from the spectrogram worker thread.
    Signals:
        finished (object): Carries the spectrogram image.
        error (): Signal emitted on error.
    """
    finished = pyqtSignal(object)  # Carries the spectrogram image
    error = pyqtSignal()  # Signal emitted on error

class SpectrogramWorker(QRunnable):
    """
    Worker thread for generating spectrogram image.

    Args:
        parent (QWidget): Parent widget.
        audio_data (np.ndarray): Audio data for spectrogram.
        sample_rate (int): Audio sample rate in Hz.
        pre_calculated_fft (list): Pre-calculated FFT data.
        audio_analyzer: Analyzer object with perform_fft_with_magnitudes method.
    """
    def __init__(self, parent, audio_data, sample_rate, pre_calculated_fft, audio_analyzer):
        super().__init__()
        self.signals = SpectrogramSignals()
        self.parent = parent
        self.audio_data = audio_data
        self.sample_rate = sample_rate
        self.pre_calculated_fft = pre_calculated_fft
        self.audio_analyzer = audio_analyzer
        
    def run(self):
        """
        Generate the spectrogram image and emit results via signals.
        Emits:
            signals.finished (QImage): The generated spectrogram image.
            signals.error (): Signal emitted on error.
        """
        try:
            # Generate spectrogram using pre-calculated FFT if available
            if self.pre_calculated_fft:
                spectrogram = self.parent._generate_spectrogram_from_fft_data(self.pre_calculated_fft)
            else:
                spectrogram = self.parent._generate_spectrogram_from_audio(
                    self.audio_data, self.sample_rate)
            
            # Signal completion with resulting image
            try:
                self.signals.finished.emit(spectrogram)
            except RuntimeError as rte:
                logger.error(f"Error in SpectrogramWorker Signal failed: {rte}") 
        except Exception as e:
            logger.error(f"Error generating spectrogram: {e}", exc_info=True)
            try:
                self.signals.error.emit()
            except RuntimeError as rte:
                logger.error(f"Error in exception SpectrogramWorker signal failed: {rte}")

class SpectrogramDisplay(QWidget):
    """
    A PyQt widget for displaying audio spectrograms with real-time updates.
    Provides frequency analysis visualization using native library FFT data.
    """

    def __init__(self, parent=None):
        """
        Initialize the SpectrogramDisplay widget with default settings.

        Args:
            parent (QWidget, optional): Parent widget.
        """
        super().__init__(parent)
        
        self.setMinimumHeight(100)  # Increased height for better visibility
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)  # Allow vertical expansion
        self.audio_analyzer = None
        self._cached_audio_data = None
        self._cached_sample_rate = None
        self._has_spectrogram = False
        self._position = 0
        self._duration = 0
        self._current_file_path = None
        self._pre_calculated_fft = None
        
        # FFT and spectrogram parameters
        self.window_size = 2048  # Window size for FFT
        self.hop_length = self.window_size // 4  # Default hop length (75% overlap)
        
        # Spectrogram image and cache
        self._spectrogram_image = None
        self._palette = self._generate_professional_palette()
        
        # Visual settings optimized for compact display
        self._axis_margin_left = 30    # Reduced space for frequency labels
        self._axis_margin_right = 3    # Minimal right margin
        self._axis_margin_top = 3      # Minimal top margin  
        self._axis_margin_bottom = 15  # Reduced space for time labels
        self._freq_grid_lines = True
        self._time_grid_lines = True
        self._show_colorbar = False  # Optional colorbar
        self._min_freq_display = 20    # Minimum frequency to display (Hz)
        self._max_freq_display = 20000 # Maximum frequency to display (Hz)
        
        # EQ band visualization settings
        self._show_eq_bands = True
        self._bass_limit_hz = 250
        self._mid_limit_hz = 4000
        self._eq_gains = {
            'bass': 1.0,
            'mid': 1.0,
            'treble': 1.0
        }
        
        # Thread pool for background processing
        self.thread_pool = QThreadPool.globalInstance()
        self._is_generating_spectrogram = False
        
        # Set custom stylesheet for completely black background
        self.setStyleSheet("""
            SpectrogramDisplay {
                background-color: #000000;
                border: 1px solid #444444;
                border-radius: 4px;
            }
        """)
    
    def _generate_professional_palette(self):
        """
        Generate a professional high-contrast color palette for spectrograms.

        Returns:
            list: List of 256 RGB color values.
        """
        # Create a custom palette that goes from black -> dark blue -> blue -> cyan -> yellow -> red -> white
        # This provides excellent contrast and is commonly used in professional audio tools
        
        palette = []
        num_colors = 256
        
        # Define key colors for the gradient (in RGB)
        key_colors = [
            (0, 0, 0),        # Black (silence)
            (0, 0, 64),       # Dark blue (very low)
            (0, 0, 128),      # Blue (low)
            (0, 64, 255),     # Light blue (low-mid)
            (0, 255, 255),    # Cyan (mid)
            (128, 255, 128),  # Light green (mid-high)
            (255, 255, 0),    # Yellow (high)
            (255, 128, 0),    # Orange (higher)
            (255, 0, 0),      # Red (very high)
            (255, 255, 255)   # White (maximum)
        ]
        
        # Interpolate between key colors
        segments = len(key_colors) - 1
        colors_per_segment = num_colors // segments
        
        for segment in range(segments):
            start_color = key_colors[segment]
            end_color = key_colors[segment + 1]
            
            for i in range(colors_per_segment):
                if segment == segments - 1 and i == colors_per_segment - 1:
                    # Handle the last color to ensure we have exactly 256 colors
                    continue
                    
                ratio = i / colors_per_segment
                r = int(start_color[0] + (end_color[0] - start_color[0]) * ratio)
                g = int(start_color[1] + (end_color[1] - start_color[1]) * ratio)
                b = int(start_color[2] + (end_color[2] - start_color[2]) * ratio)
                
                palette.append(qRgb(r, g, b))
        
        # Ensure we have exactly 256 colors
        while len(palette) < 256:
            palette.append(qRgb(255, 255, 255))
        
        palette = palette[:256]  # Trim if over 256
        return palette
    
    def set_current_file_path_spectrogram(self, file_path):
        """
        Set the current file path.

        Args:
            file_path (str): Path to the current audio file.
        """
        self._current_file_path = file_path
                
    def set_fft_analyzer(self, analyzer):
        """
        Set the audio analyzer for FFT calculations.

        Args:
            analyzer: Audio analyzer instance.
        """
        self.audio_analyzer = analyzer
        
    def set_spectrum_data(self, audio_data, sample_rate):
        """
        Set audio data for spectrogram generation.

        Args:
            audio_data (np.ndarray): Audio data array.
            sample_rate (int): Audio sample rate in Hz.
        """
        self._cached_audio_data = audio_data
        self._cached_sample_rate = sample_rate
        self._has_spectrogram = False
        
        # Generate a quick low-res preview immediately
        self._generate_low_res_preview()
        
        # Generate the spectrogram in background after a short delay
        QTimer.singleShot(100, self._generate_spectrogram_async)
        
    def _generate_low_res_preview(self):
        """
        Generate a quick low-resolution spectrogram preview for immediate display.
        """
        if not self.audio_analyzer or self._cached_audio_data is None:
            return
            
        try:
            # Use larger hop and lower resolution for quick preview
            preview_window_size = 1024
            preview_hop_length = preview_window_size
            
            # Downsample for very long tracks
            audio_data = self._cached_audio_data
            sample_rate = self._cached_sample_rate
            audio_duration_sec = len(audio_data) / sample_rate
            
            # Determine downsampling rate based on duration
            downsample = 1
            if audio_duration_sec > 180:  # 3+ minutes
                downsample = max(1, int(audio_duration_sec / 180))
                
            if downsample > 1:
                # Simple downsampling - take every Nth sample
                audio_data = audio_data[::downsample]
                
            # Convert to mono if needed
            audio_data = np.mean(audio_data, axis=1) if audio_data.ndim > 1 else audio_data
            
            # Calculate reduced number of frames for preview
            audio_len = len(audio_data)
            max_frames = min(self.width(), 100)  # Limit frames for performance
            frame_skip = max(1, int(audio_len / (max_frames * preview_window_size)))
            
            # Calculate number of frames
            num_frames = 1 + (audio_len - preview_window_size) // preview_hop_length
            num_freq_bins = preview_window_size // 2 + 1
            spectrogram = np.zeros((num_freq_bins, num_frames // frame_skip + 1))
            
            # Create window function once using C++ implementation
            if self.audio_analyzer and hasattr(self.audio_analyzer, 'get_hanning_window'):
                window_func = self.audio_analyzer.get_hanning_window(preview_window_size)
                if window_func is None:
                    # Fallback to Python implementation
                    window_func = np.hanning(preview_window_size)
            else:
                # Fallback to Python implementation
                window_func = np.hanning(preview_window_size)
            
            # Process frames with large stride for preview
            frame_idx = 0
            for i in range(0, num_frames, frame_skip):
                start = i * preview_hop_length
                end = start + preview_window_size
                
                if end <= audio_len:
                    window = audio_data[start:end] * window_func
                    # Use optimized FFT with magnitudes if available
                    magnitudes = self.audio_analyzer.perform_fft_with_magnitudes(window)
                    
                    if magnitudes is not None and len(magnitudes) > 0:
                        spectrogram[:len(magnitudes), frame_idx] = magnitudes[:num_freq_bins]
                        frame_idx += 1
            
            # Trim unused space
            spectrogram = spectrogram[:, :frame_idx]
            
            # Apply professional processing
            spectrogram = self._process_spectrogram_for_display(spectrogram)
            
            # Create QImage with the professional palette
            image = self._create_spectrogram_image(spectrogram)
            
            if image and not image.isNull():
                self._spectrogram_image = image
                self._has_spectrogram = True
                self.update()  # Trigger repaint with preview
                logger.debug(f"Generated low-res preview spectrogram: {spectrogram.shape[1]}x{spectrogram.shape[0]}")
            
        except Exception as e:
            logger.error(f"Error generating spectrogram preview: {e}", exc_info=True)
            # Continue to full resolution generation even if preview fails
    
    def _process_spectrogram_for_display(self, spectrogram):
        """Process spectrogram data for optimal visual display."""
        # Try to use C++ implementation if available
        if hasattr(self, 'audio_analyzer') and self.audio_analyzer and hasattr(self.audio_analyzer, 'process_spectrogram'):
            try:
                processed = self.audio_analyzer.process_spectrogram(spectrogram.astype(np.float32))
                if processed is not None:
                    return processed
                # If C++ processing fails, fall back to Python implementation
                logger.debug("C++ spectrogram processing failed, falling back to Python implementation")
            except Exception as e:
                logger.debug(f"C++ spectrogram processing error: {e}, falling back to Python implementation")

        # Python implementation as fallback
        # Apply logarithmic scaling for better dynamic range
        spectrogram = np.log10(spectrogram + 1e-10)
        
        # Apply dynamic range compression (enhance contrast)
        # Use percentile-based normalization for better visual results
        p1, p99 = np.percentile(spectrogram, [1, 99])
        dynamic_range_db = 60  # 60dB dynamic range for professional look
        
        # Clip and normalize
        spectrogram = np.clip(spectrogram, p99 - dynamic_range_db/10, p99)
        spectrogram = (spectrogram - (p99 - dynamic_range_db/10)) / (dynamic_range_db/10)
        
        # Apply slight gamma correction for better mid-range visibility
        gamma = 0.7
        spectrogram = np.power(spectrogram, gamma)
        
        # Scale to 0-255 range
        spectrogram = np.clip(spectrogram * 255, 0, 255).astype(np.uint8)
        
        return spectrogram
    
    def _create_spectrogram_image(self, spectrogram):
        """Create a QImage from spectrogram data."""
        try:
            # Flip vertically so low frequencies are at bottom (standard orientation)
            spectrogram = np.flipud(spectrogram)
            spectrogram_data = np.ascontiguousarray(spectrogram)
            
            # Create QImage
            height, width = spectrogram.shape
            image = QImage(spectrogram_data.data, width, height, width, QImage.Format.Format_Indexed8)
            
            if not image.isNull():
                image.setColorTable(self._palette)
                return image
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error creating spectrogram image: {e}", exc_info=True)
            return None
    
    def _generate_spectrogram_async(self):
        """Generate the spectrogram image in a background thread."""
        if not self.audio_analyzer or self._cached_audio_data is None or self._is_generating_spectrogram:
            return
            
        self._is_generating_spectrogram = True
        
        # Create and setup worker
        worker = SpectrogramWorker(
            self, 
            self._cached_audio_data, 
            self._cached_sample_rate,
            self._pre_calculated_fft,
            self.audio_analyzer
        )
        
        # Connect signals
        worker.signals.finished.connect(self._on_spectrogram_generated)
        worker.signals.error.connect(self._on_spectrogram_error)
        
        # Start the worker
        self.thread_pool.start(worker)
    
    def _on_spectrogram_generated(self, spectrogram):
        """Slot called when spectrogram generation completes."""
        self._spectrogram_image = spectrogram
        self._has_spectrogram = spectrogram is not None
        self._is_generating_spectrogram = False
        self.update()
        
    def _on_spectrogram_error(self):
        """Slot called when spectrogram generation fails."""
        self._has_spectrogram = False
        self._is_generating_spectrogram = False
        self.update()
    
    def update_eq_gains(self, bass_gain, mid_gain, treble_gain):
        """Update EQ gain values for visualization."""
        self._eq_gains = {
            'bass': bass_gain,
            'mid': mid_gain,
            'treble': treble_gain
        }
        self.update()
        
    def _generate_spectrogram_from_fft_data(self, fft_data):
        """Generate spectrogram image using pre-calculated FFT data."""
        try:
            # Extract FFT magnitudes from pre-calculated data
            fft_times = []
            fft_magnitudes = []
            
            for entry in fft_data:
                fft_times.append(entry['time_ms'])
                fft_magnitudes.append(entry['magnitudes'])
            
            if not fft_magnitudes:
                return None
                
            # Convert to numpy arrays
            fft_magnitudes = [np.array(m, dtype=np.float32) if isinstance(m, list) else m 
                             for m in fft_magnitudes]
            
            # Get dimensions
            num_frames = len(fft_magnitudes)
            num_freq_bins = len(fft_magnitudes[0]) if num_frames > 0 else 0
            
            if num_frames == 0 or num_freq_bins == 0:
                return None
                
            # Create spectrogram array
            spectrogram = np.zeros((num_freq_bins, num_frames), dtype=np.float32)
            
            # Fill the spectrogram with FFT data
            for i, magnitudes in enumerate(fft_magnitudes):
                spectrogram[:, i] = magnitudes
            
            # Process for professional display
            spectrogram = self._process_spectrogram_for_display(spectrogram)
            
            # Create the image
            return self._create_spectrogram_image(spectrogram)
                
        except Exception as e:
            logger.error(f"Error generating spectrogram from FFT data: {e}", exc_info=True)
            return None
            
    def _generate_spectrogram_from_audio(self, audio_data, sample_rate):
        """Generate the spectrogram image from audio data using native library FFT."""
        try:
            # Parameters for the spectrogram
            window_size = self.window_size  # Use class attribute
            hop_length = self.hop_length    # Use class attribute
            num_freq_bins = window_size // 2 + 1  # Number of frequency bins
            
            # Add adaptive resolution based on audio length
            audio_duration_sec = len(audio_data) / sample_rate
            if audio_duration_sec > 300:  # 5+ minutes
                # For very long tracks, skip frames to maintain reasonable processing time
                frame_skip = max(1, int(audio_duration_sec / 300))
            else:
                frame_skip = 1
            
            # Convert to mono if needed
            audio_data = np.mean(audio_data, axis=1) if audio_data.ndim > 1 else audio_data
            
            # Calculate number of frames
            audio_len = len(audio_data)
            num_frames = 1 + (audio_len - window_size) // hop_length
            spectrogram = np.zeros((num_freq_bins, num_frames))
            
            # Pre-allocate numpy arrays once, outside the loop
            # Create window function using C++ implementation
            if self.audio_analyzer and hasattr(self.audio_analyzer, 'get_hanning_window'):
                window_func = self.audio_analyzer.get_hanning_window(window_size)
                if window_func is None:
                    # Fallback to Python implementation
                    window_func = np.hanning(window_size)
            else:
                # Fallback to Python implementation
                window_func = np.hanning(window_size)
            
            # Process each window using native library FFT
            for i in range(0, num_frames, frame_skip):
                start = i * hop_length
                end = start + window_size
                if end <= audio_len:
                    window = audio_data[start:end] * window_func
                    # Use optimized FFT with magnitudes if available
                    magnitudes = self.audio_analyzer.perform_fft_with_magnitudes(window)
                    
                    if magnitudes is not None and len(magnitudes) > 0:
                        spectrogram[:len(magnitudes), i] = magnitudes[:num_freq_bins]
            
            # Process for professional display
            spectrogram = self._process_spectrogram_for_display(spectrogram)
            
            # Create the image
            return self._create_spectrogram_image(spectrogram)
            
        except Exception as e:
            logger.error(f"Error generating spectrogram from audio: {e}", exc_info=True)
            return None
    
    def update_position(self, position, duration):
        """Update the current position indicator without redrawing the entire spectrogram."""
        if duration <= 0:
            return
            
        old_position_x = int((self.width() - self._axis_margin_left - self._axis_margin_right) * self._position / self._duration + self._axis_margin_left) if self._duration > 0 else 0
        self._position = position
        self._duration = duration
        
        # Only redraw if we have a valid spectrogram
        if self._has_spectrogram and self._spectrogram_image and not self._spectrogram_image.isNull():
            new_position_x = int((self.width() - self._axis_margin_left - self._axis_margin_right) * position / duration) + self._axis_margin_left
            
            # Calculate the region to update (just the playhead area)
            update_rect_width = max(3, abs(new_position_x - old_position_x) + 2)
            update_x = min(old_position_x, new_position_x) - 1
            
            if update_x < 0:
                update_x = 0
            if update_x + update_rect_width > self.width():
                update_rect_width = self.width() - update_x
                
            # Only update the area that changed, not the whole widget
            if update_rect_width > 0:
                self.update(update_x, 0, update_rect_width, self.height())
        else:
            # If no spectrogram yet, update the whole widget
            self.update()

    def _get_y_position_for_frequency(self, freq_hz, height):
        """Calculate the Y position for a given frequency."""
        if not self._cached_sample_rate or freq_hz <= 0:
            return height
            
        # Account for axis margins
        effective_height = height - self._axis_margin_top - self._axis_margin_bottom
        
        nyquist = self._cached_sample_rate / 2
        min_freq = max(self._min_freq_display, 1)
        max_freq = min(self._max_freq_display, nyquist)
        
        # Clamp frequency to display range
        freq_hz = max(min_freq, min(freq_hz, max_freq))
        
        # Logarithmic scale
        log_min = np.log10(min_freq)
        log_max = np.log10(max_freq)
        log_freq = np.log10(freq_hz)
        
        # Calculate ratio and Y position
        ratio = (log_freq - log_min) / (log_max - log_min)
        y_in_spec = effective_height * (1.0 - ratio)  # Invert Y axis
        
        return int(y_in_spec + self._axis_margin_top)
        
    def paintEvent(self, event):
        """Render the professional spectrogram visualization."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        height = self.height()
        
        # Fill with completely black background
        painter.fillRect(0, 0, width, height, QColor(0, 0, 0))
        
        # Calculate display areas with optimized margins
        spec_x = self._axis_margin_left
        spec_y = self._axis_margin_top
        spec_width = width - self._axis_margin_left - self._axis_margin_right
        spec_height = height - self._axis_margin_top - self._axis_margin_bottom
        
        # Check if we need to generate the spectrogram
        if not self._has_spectrogram and self._cached_audio_data is not None and not self._is_generating_spectrogram:
            # Start async generation if not already in progress
            self._generate_spectrogram_async()
            # Draw loading text
            painter.setPen(QColor(150, 150, 150))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(QRect(spec_x, spec_y, spec_width, spec_height), 
                           Qt.AlignmentFlag.AlignCenter, "Generating spectrogram...")
            return
        
        # Draw spectrogram if available
        if self._has_spectrogram and self._spectrogram_image and not self._spectrogram_image.isNull():
            # Draw the spectrogram with smooth scaling
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(QRect(spec_x, spec_y, spec_width, spec_height), self._spectrogram_image)
            
            # Draw frequency axis (Y-axis)
            self._draw_frequency_axis(painter, spec_x, spec_y, spec_height)
            
            # Draw time axis (X-axis)
            self._draw_time_axis(painter, spec_x, spec_y + spec_height, spec_width)
            
            # Draw position line
            if self._duration > 0:
                position_x = spec_x + int(spec_width * self._position / self._duration)
                painter.setPen(QPen(QColor(243, 207, 44), 2))
                painter.drawLine(position_x, spec_y, position_x, spec_y + spec_height)
            
            # Draw EQ bands if enabled
            if self._show_eq_bands:
                self._draw_eq_bands(painter, spec_x, spec_y, spec_width, spec_height)
                
        elif self._is_generating_spectrogram:
            # Show loading indicator
            painter.setPen(QColor(150, 150, 150))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(QRect(spec_x, spec_y, spec_width, spec_height), 
                           Qt.AlignmentFlag.AlignCenter, "Generating spectrogram...")
        else:
            # Draw placeholder text
            painter.setPen(QColor(100, 100, 100))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(QRect(spec_x, spec_y, spec_width, spec_height), 
                           Qt.AlignmentFlag.AlignCenter, "No audio data available...")
    
    def _draw_frequency_axis(self, painter, x, y, height):
        """Draw the frequency axis with labels and grid lines."""
        if not self._cached_sample_rate:
            return
            
        painter.setPen(QColor(180, 180, 180))
        painter.setFont(QFont("Arial", 6))  # Smaller font for compact display
        
        # Define frequency points to label (logarithmic distribution)
        freq_points = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
        nyquist = self._cached_sample_rate / 2
        
        for freq in freq_points:
            if freq > nyquist:
                break
                
            y_pos = self._get_y_position_for_frequency(freq, y + height)
            
            # Draw grid line if enabled
            if self._freq_grid_lines:
                painter.setPen(QPen(QColor(60, 60, 60), 1, Qt.PenStyle.DashLine))
                painter.drawLine(x, y_pos, x + self.width() - self._axis_margin_left - self._axis_margin_right, y_pos)
            
            # Draw tick mark
            painter.setPen(QColor(180, 180, 180))
            painter.drawLine(x - 5, y_pos, x, y_pos)
            
            # Draw label
            if freq >= 1000:
                label = f"{freq//1000}kHz"
            else:
                label = f"{freq}Hz"
                
            text_rect = painter.fontMetrics().boundingRect(label)
            painter.drawText(x - text_rect.width() - 8, y_pos + text_rect.height()//2, label)
    
    def _draw_time_axis(self, painter, x, y, width):
        """Draw the time axis with labels and grid lines."""
        if self._duration <= 0:
            return
            
        painter.setPen(QColor(180, 180, 180))
        painter.setFont(QFont("Arial", 5))  # Smaller font to match frequency axis
        
        # Calculate time intervals
        duration_sec = self._duration / 1000.0
        
        # Choose appropriate time interval
        if duration_sec <= 30:
            interval_sec = 5
        elif duration_sec <= 120:
            interval_sec = 10
        elif duration_sec <= 300:
            interval_sec = 30
        else:
            interval_sec = 60
        
        # Draw time markers
        current_time = 0
        while current_time <= duration_sec:
            x_pos = x + int(width * (current_time * 1000) / self._duration)
            
            # Draw grid line if enabled
            if self._time_grid_lines:
                painter.setPen(QPen(QColor(60, 60, 60), 1, Qt.PenStyle.DashLine))
                painter.drawLine(x_pos, self._axis_margin_top, x_pos, y)
            
            # Draw tick mark
            painter.setPen(QColor(180, 180, 180))
            painter.drawLine(x_pos, y, x_pos, y + 5)
            
            # Draw label
            minutes = int(current_time // 60)
            seconds = int(current_time % 60)
            label = f"{minutes}:{seconds:02d}"
            
            text_rect = painter.fontMetrics().boundingRect(label)
            painter.drawText(x_pos - text_rect.width()//2, y + text_rect.height() + 5, label)
            
            current_time += interval_sec
    
    def _draw_eq_bands(self, painter, x, y, width, height):
        """Draw EQ band visualizations with professional styling."""
        # Calculate band positions
        bass_y = self._get_y_position_for_frequency(self._bass_limit_hz, y + height)
        mid_y = self._get_y_position_for_frequency(self._mid_limit_hz, y + height)
        
        # Draw band regions with gain-based opacity
        bass_opacity = max(20, min(80, int(40 * self._eq_gains['bass'])))
        mid_opacity = max(20, min(80, int(40 * self._eq_gains['mid'])))
        treble_opacity = max(20, min(80, int(40 * self._eq_gains['treble'])))
        
        # Bass region (bottom)
        painter.fillRect(x, bass_y, width, y + height - bass_y, 
                        QColor(255, 100, 100, bass_opacity))
        
        # Mid region (middle)
        painter.fillRect(x, mid_y, width, bass_y - mid_y, 
                        QColor(100, 255, 100, mid_opacity))
        
        # Treble region (top)
        painter.fillRect(x, y, width, mid_y - y, 
                        QColor(100, 100, 255, treble_opacity))
        
        # Draw frequency band boundaries
        painter.setPen(QPen(QColor(243, 207, 44, 180), 1, Qt.PenStyle.DashLine))
        painter.drawLine(x, bass_y, x + width, bass_y)
        painter.drawLine(x, mid_y, x + width, mid_y)
        
        # Draw gain labels in the top-right corner
        painter.setFont(QFont("Arial", 5))  # Smaller font to match other labels
        painter.setPen(QColor(243, 207, 44))
        
        label_x = x + width - 80
        painter.fillRect(label_x - 5, y + 5, 75, 50, QColor(0, 0, 0, 160))
        
        painter.drawText(label_x, y + 15, f"Treble: {self._eq_gains['treble']:.1f}x")
        painter.drawText(label_x, y + 28, f"Mid: {self._eq_gains['mid']:.1f}x")
        painter.drawText(label_x, y + 41, f"Bass: {self._eq_gains['bass']:.1f}x") 