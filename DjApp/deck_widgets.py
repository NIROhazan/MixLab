import os
import time
import traceback
import unicodedata
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QFileDialog, QSizePolicy, QMessageBox,
    QLineEdit, QDial
)
from PyQt6.QtCore import (
    Qt, QTimer, QUrl, pyqtSignal, QThread, QRectF
)
from PyQt6.QtGui import  QColor, QLinearGradient, QPainter, QBrush, QPen, QPainterPath, QIntValidator
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
import soundfile as sf
from waveform import WaveformDisplay, SpectrogramDisplay
from turntable import Turntable
from equalizer import ThreeBandEQ

def safe_filename_for_logging(filepath):
    """
    Safely display a filename for console logging that may contain Hebrew or Unicode characters.
    Returns ASCII-safe representation for logging and error messages only.
    
    Args:
        filepath (str): The file path that may contain Unicode characters.
        
    Returns:
        str: ASCII-safe representation of the filename for logging.
    """
    if not filepath:
        return "None"
    
    try:
        filename = os.path.basename(filepath)
        # Try to normalize and encode safely
        safe_name = unicodedata.normalize('NFKD', filename)
        # Keep only ASCII characters for safe display
        ascii_name = ''.join(c for c in safe_name if c.isascii())
        
        # If we lost all characters, use a generic identifier
        if not ascii_name.strip():
            ascii_name = f"<Unicode-filename-{hash(filename) % 10000}>"
        
        return ascii_name
    except Exception as e:
        # Fallback if any encoding issues occur
        return f"<filename-error-{hash(str(filepath)) % 10000}>"

def get_display_filename(filepath):
    """
    Get the filename for UI display, preserving Hebrew and Unicode characters.
    
    Args:
        filepath (str): The file path.
        
    Returns:
        str: The original filename for display in UI.
    """
    if not filepath:
        return "No track loaded"
    
    try:
        return os.path.basename(filepath)
    except Exception as e:
        return "Error reading filename"

class GlassWidget(QWidget):
    """
    A custom widget that implements a glass-like effect with hover state handling.

    This widget serves as a base class for deck-related UI elements with a translucent
    appearance and hover effects.
    """

    def __init__(self, parent=None):
        """
        Initialize the GlassWidget.

        Args:
            parent (QWidget, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.setMouseTracking(True)
        
        self._hover_opacity = 0.0
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(16)  # ~60fps
        self._animation_timer.timeout.connect(self._update_hover)
        self._target_opacity = 0.0
        
        # Theme color for hover effects (default to neon yellow)
        self._theme_accent_color = QColor(243, 207, 44)
        
    def enterEvent(self, event):
        """
        Handle mouse enter events to update hover state.

        Args:
            event: The QEnterEvent instance.
        """
        self._target_opacity = 0.25
        if not self._animation_timer.isActive():
            self._animation_timer.start()
        
    def leaveEvent(self, event):
        """
        Handle mouse leave events to update hover state.

        Args:
            event: The QLeaveEvent instance.
        """
        self._target_opacity = 0.0
        if not self._animation_timer.isActive():
            self._animation_timer.start()
        
    def _update_hover(self):
        """
        Update the widget's hover state and trigger a repaint.
        """
        if abs(self._hover_opacity - self._target_opacity) < 0.01:
            self._hover_opacity = self._target_opacity
            self._animation_timer.stop()
        else:
            self._hover_opacity += (self._target_opacity - self._hover_opacity) * 0.2
        
        self.update()
        
    def paintEvent(self, event):
        """
        Paint the widget with a glass-like effect.

        Args:
            event: The QPaintEvent instance.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor(255, 255, 255, 25))
        gradient.setColorAt(1, QColor(255, 255, 255, 10))
        
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, 15, 15)
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawPath(path)
        
        if self._hover_opacity > 0:
            glow = QColor(self._theme_accent_color.red(), self._theme_accent_color.green(), 
                         self._theme_accent_color.blue(), int(self._hover_opacity * 255))
            painter.setBrush(QBrush(glow))
            painter.drawPath(path)
        
        border_color = QColor(255, 255, 255, 40)
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        
        highlight = QLinearGradient(0, 0, 0, self.height() * 0.5)
        highlight.setColorAt(0, QColor(255, 255, 255, 30))
        highlight.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(highlight))
        painter.drawPath(path)
        
        if self._hover_opacity > 0:
            glow_color = QColor(self._theme_accent_color.red(), self._theme_accent_color.green(), 
                               self._theme_accent_color.blue(), int(20 * self._hover_opacity))
            for i in range(3):
                painter.setPen(QPen(glow_color, i * 2 + 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)

class TempoChangeWorker(QThread):
    """
    QThread worker for performing tempo changes on audio files in the background.
    """
    finished = pyqtSignal(int, str, bool, int, object, bool) 
    error = pyqtSignal(int, str)

    def __init__(self, deck_num, analyzer, original_file_path_for_worker, temp_output_path, factor, original_length_sec, target_bpm, target_pos_on_load, was_playing_state):
        """
        Initialize the TempoChangeWorker.

        Args:
            deck_num (int): Deck number.
            analyzer (AudioAnalyzerBridge): Audio analyzer bridge instance.
            original_file_path_for_worker (str): Path to the original audio file.
            temp_output_path (str): Path for the output file.
            factor (float): Stretch factor for tempo change.
            original_length_sec (float): Original length of the audio in seconds.
            target_bpm (int): Target BPM after processing.
            target_pos_on_load (object): Target position after loading.
            was_playing_state (bool): Whether playback was active before processing.
        """
        super().__init__()
        self.deck_number = deck_num
        self.audio_analyzer = analyzer
        self.original_file_path = original_file_path_for_worker
        self.temp_output_file = temp_output_path
        self.stretch_factor = factor
        self.length_seconds_of_original = original_length_sec 
        self.target_bpm = target_bpm
        self.target_position_after_load = target_pos_on_load
        self.was_playing_flag = was_playing_state

    def run(self):
        """
        Execute the tempo change operation. Emits signals on completion or error.
        """
        success = False
        try:
            print(f"Worker (Deck {self.deck_number}): Starting tempo change. Original='{safe_filename_for_logging(self.original_file_path)}', Factor={self.stretch_factor:.3f}, OrigLenSec={self.length_seconds_of_original:.2f}")
            if not self.original_file_path or not os.path.exists(self.original_file_path):
                raise FileNotFoundError(f"Worker (Deck {self.deck_number}): Original file for tempo change not found: {self.original_file_path}")

            # Call the AudioAnalyzer's method to change tempo
            success = self.audio_analyzer.change_tempo(
                self.original_file_path, 
                self.temp_output_file, 
                self.stretch_factor, 
                self.length_seconds_of_original
            )
            
            if success:
                 if not os.path.exists(self.temp_output_file) or os.path.getsize(self.temp_output_file) == 0:
                     print(f"Worker (Deck {self.deck_number}): Output file '{safe_filename_for_logging(self.temp_output_file)}' invalid after change_tempo reported success!"); success = False
                     try: os.remove(self.temp_output_file) 
                     except OSError: pass 
            else:
                print(f"Worker (Deck {self.deck_number}): audio_analyzer.change_tempo reported failure.")

            self.finished.emit(self.deck_number, self.temp_output_file, success, self.target_bpm, self.target_position_after_load, self.was_playing_flag)
        except FileNotFoundError as fnf_e:
            error_msg = f"Worker (Deck {self.deck_number}) FileNotFoundError: {fnf_e}"
            print(error_msg); traceback.print_exc()
            self.error.emit(self.deck_number, error_msg)
        except Exception as e:
             error_msg = f"Worker (Deck {self.deck_number}) Exception in TempoChangeWorker: {type(e).__name__}: {e} (File: {safe_filename_for_logging(self.original_file_path)})"
             print(error_msg); traceback.print_exc()
             # Attempt to clean up failed output file
             if os.path.exists(self.temp_output_file):
                 try: os.remove(self.temp_output_file)
                 except OSError: pass
             self.error.emit(self.deck_number, error_msg)

class DeckWidget(GlassWidget):
    """
    Main deck widget for audio playback, visualization, tempo/EQ control, and user interaction.
    """
    volumeChanged = pyqtSignal()
    tempoProcessing = pyqtSignal(bool)

    def __init__(self, deck_number, main_app, audio_analyzer, parent=None):
        """
        Initialize the DeckWidget.

        Args:
            deck_number (int): Deck number.
            main_app: Reference to the main application.
            audio_analyzer: Audio analyzer bridge instance.
            parent (QWidget, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.deck_number = deck_number
        self.main_app = main_app
        self.audio_analyzer = audio_analyzer
        self.current_file = None
        self.original_file_path = None  # Always keep reference to the original file
        self.temp_file = None
        self._is_playing = False
        self.original_bpm = 0
        self.current_bpm = 0
        self.beat_positions = []
        self._current_volume = 1.0
        self._seek_after_load_fraction = None
        self._resume_after_load = False
        self.sync_button = None
        self.tempo_worker = None
        
        # Add loop state variables
        self._loop_enabled = False
        self._loop_start_time = 0  # in milliseconds
        self._loop_length = 4000   # default 4 seconds in milliseconds
        self._loop_end_time = 0    # calculated from start + length
        
        self._last_position_update = 0
        self._position_update_interval = 16
        self._last_ui_update = 0
        self._ui_update_interval = 100
        self._last_eq_output_file = None
        self._load_retries = 0
        
        self.position_timer = QTimer()
        self.position_timer.setInterval(16)
        self.position_timer.timeout.connect(self._position_timer_tick)
        
        # Create a new QMediaPlayer instance with a unique audio output for each deck
        self.player = QMediaPlayer()
        
        # Get available audio output devices
        available_devices = QMediaDevices.audioOutputs()
        default_device = QMediaDevices.defaultAudioOutput()
        
        # Create a unique audio output for this deck
        if available_devices:
            # Create a unique audio output instance for each deck
            if default_device and not default_device.isNull():
                print(f"Deck {self.deck_number}: Creating unique audio output instance using default device: {default_device.description()}")
                self.audio_output = QAudioOutput(default_device)
            else:
                # Fallback to first available device if no default
                print(f"Deck {self.deck_number}: Using first available Audio Output Device: {available_devices[0].description()}")
                self.audio_output = QAudioOutput(available_devices[0])
        else:
            print(f"Deck {self.deck_number}: WARNING - No audio output device found! Using default constructor.")
            self.audio_output = QAudioOutput()
            
        # Connect the audio output to the player
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(1.0) 
        print(f"Deck {self.deck_number}: Setting initial volume to 1.0")
        self.audio_output.setMuted(False)
    
        self.player.durationChanged.connect(self.update_duration)
        self.player.errorOccurred.connect(self.handle_player_error)
        self.player.playbackStateChanged.connect(self._update_turntable_state)
        
        self.turntable = Turntable()
        self.turntable.positionScrubbed.connect(self.adjust_position_from_turntable)
        self.turntable.pitchChanged.connect(self.adjust_playback_rate)
        
        self.equalizer = ThreeBandEQ(audio_analyzer=self.audio_analyzer)
        self._eq_bass_gain = 1.0
        self._eq_mid_gain = 1.0
        self._eq_treble_gain = 1.0
        
        self.setup_ui()


    def setup_ui(self):
        """
        Set up the user interface for the deck, including controls, waveform, spectrogram, EQ, and loop controls.
        """
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        self.track_label = QLabel("No track loaded")
        self.track_label.setObjectName("displayLabel")
        self.track_label.setWordWrap(True)
        self.track_label.setMinimumHeight(40)
        
        self.waveform = WaveformDisplay()
        self.waveform.set_audio_analyzer_with_cache(self.audio_analyzer)
        self.waveform.setProperty("class", "waveformDisplay")
        
        self.spectrogram = SpectrogramDisplay()
        self.spectrogram.set_fft_analyzer(self.audio_analyzer)
        self.spectrogram.setProperty("class", "spectrogramDisplay")
        
        # Create a container widget for visualizations with optimized layout
        viz_container = QWidget()
        viz_layout = QVBoxLayout(viz_container)
        viz_layout.setContentsMargins(0, 0, 0, 0)  # No margins for maximum space usage
        viz_layout.setSpacing(2)  # Minimal spacing
        viz_layout.addWidget(self.waveform, 65)     # Give 65% of space to waveform
        viz_layout.addWidget(self.spectrogram, 35)  # Give 35% of space to spectrogram (visible but balanced)
        
        controls_panel = QWidget()
        controls_panel.setObjectName("glassPanel")
        controls_layout = QHBoxLayout(controls_panel)
        controls_layout.setSpacing(10)
        
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.toggle_playback)
        self.play_btn.setProperty("class", "neonBorder")
        
        self.volume_slider = QSlider(Qt.Orientation.Vertical)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(100)
        self.volume_slider.setMaximumHeight(80)
        self.volume_slider.setProperty("class", "volumeSliderNormal")
        self.volume_slider.valueChanged.connect(self.handle_volume_change)
        
        tempo_panel = QWidget()
        tempo_panel.setObjectName("glassPanel")
        tempo_layout = QVBoxLayout(tempo_panel)
        
        bpm_display_layout = QHBoxLayout()
        tempo_label = QLabel("BPM:")
        self.tempo_text = QLineEdit()
        self.tempo_text.setPlaceholderText("Enter BPM")
        self.tempo_text.setValidator(QIntValidator(0, 1000))
        self.tempo_text.returnPressed.connect(self.handle_bpm_input)
        
        bpm_display_layout.addWidget(tempo_label)
        bpm_display_layout.addWidget(self.tempo_text)
        
        bpm_controls_layout = QHBoxLayout()
        tempo_down_btn = QPushButton("-")
        tempo_down_btn.setObjectName("bpm_minus")
        tempo_down_btn.clicked.connect(lambda: self.adjust_tempo(-1))
        
        tempo_up_btn = QPushButton("+")
        tempo_up_btn.setObjectName("bpm_plus")
        tempo_up_btn.clicked.connect(lambda: self.adjust_tempo(1))
        
        tempo_reset_btn = QPushButton("Reset BPM")
        tempo_reset_btn.clicked.connect(self.reset_tempo)
        
        bpm_controls_layout.addWidget(tempo_down_btn)
        bpm_controls_layout.addWidget(tempo_up_btn)
        bpm_controls_layout.addWidget(tempo_reset_btn)
        
        tempo_layout.addLayout(bpm_display_layout)
        tempo_layout.addLayout(bpm_controls_layout)
        
        # Add tempo layout to the main layout
        layout.addLayout(tempo_layout)
        
        self.sync_button = QPushButton("SYNC")
        self.sync_button.setProperty("class", "syncDefault")
        
        self.progress = QSlider(Qt.Orientation.Horizontal)
        self.progress.setMinimum(0)
        self.progress.setMaximum(1000)
        self.progress.setProperty("class", "progressSlider")
        self.progress.sliderMoved.connect(self.seek)
        self.progress.sliderPressed.connect(lambda: self.player.pause())
        self.progress.sliderReleased.connect(lambda: self.player.play() if self.is_playing else None)

        self.current_time = QLabel("0:00")
        self.total_time = QLabel("0:00")
        self.current_time.setProperty("class", "neonText")
        self.total_time.setProperty("class", "neonText")
        
        controls_layout.addWidget(self.play_btn)
        controls_layout.addWidget(self.volume_slider)
        controls_layout.addWidget(tempo_panel)
        
        self.time_layout = QHBoxLayout()
        self.time_layout.addWidget(self.current_time)
        self.time_layout.addStretch()
        self.time_layout.addWidget(self.total_time)
        
        eq_panel = QWidget()
        eq_panel.setObjectName("glassPanel")
        eq_layout = QHBoxLayout(eq_panel)
        eq_layout.setSpacing(10)
        
        eq_label = QLabel("EQ:")
        eq_label.setProperty("class", "neonText")
        eq_layout.addWidget(eq_label)
        
        bass_layout = QVBoxLayout()
        self.bass_knob = QDial()
        self.bass_knob.setMinimum(0); self.bass_knob.setMaximum(200); self.bass_knob.setValue(100)
        self.bass_knob.setWrapping(False); self.bass_knob.setNotchesVisible(True)
        self.bass_knob.valueChanged.connect(self._on_eq_changed)
        self.bass_knob.setFixedSize(50, 50)
        bass_label = QLabel("Bass"); bass_label.setAlignment(Qt.AlignmentFlag.AlignCenter); bass_label.setProperty("class", "neonText")
        bass_layout.addWidget(self.bass_knob, 0, Qt.AlignmentFlag.AlignCenter); bass_layout.addWidget(bass_label)
        eq_layout.addLayout(bass_layout)
        
        mid_layout = QVBoxLayout()
        self.mid_knob = QDial()
        self.mid_knob.setMinimum(0); self.mid_knob.setMaximum(200); self.mid_knob.setValue(100)
        self.mid_knob.setWrapping(False); self.mid_knob.setNotchesVisible(True)
        self.mid_knob.valueChanged.connect(self._on_eq_changed)
        self.mid_knob.setFixedSize(50, 50)
        mid_label = QLabel("Mid"); mid_label.setAlignment(Qt.AlignmentFlag.AlignCenter); mid_label.setProperty("class", "neonText")
        mid_layout.addWidget(self.mid_knob, 0, Qt.AlignmentFlag.AlignCenter); mid_layout.addWidget(mid_label)
        eq_layout.addLayout(mid_layout)
        
        treble_layout = QVBoxLayout()
        self.treble_knob = QDial()
        self.treble_knob.setMinimum(0); self.treble_knob.setMaximum(200); self.treble_knob.setValue(100)
        self.treble_knob.setWrapping(False); self.treble_knob.setNotchesVisible(True)
        self.treble_knob.valueChanged.connect(self._on_eq_changed)
        self.treble_knob.setFixedSize(50, 50)
        treble_label = QLabel("Treble"); treble_label.setAlignment(Qt.AlignmentFlag.AlignCenter); treble_label.setProperty("class", "neonText")
        treble_layout.addWidget(self.treble_knob, 0, Qt.AlignmentFlag.AlignCenter); treble_layout.addWidget(treble_label)
        eq_layout.addLayout(treble_layout)
        
        reset_eq_btn = QPushButton("Reset EQ")
        reset_eq_btn.clicked.connect(self._reset_eq)
        eq_layout.addWidget(reset_eq_btn)
        
        # Add EQ status label
        self.eq_status_label = QLabel("")
        self.eq_status_label.setProperty("class", "neonText")
        self.eq_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.eq_status_label.setVisible(False)  # Hidden by default
        eq_layout.addWidget(self.eq_status_label)
        
        layout.addWidget(self.track_label)
        layout.addWidget(viz_container)
        layout.addWidget(eq_panel)
        layout.addWidget(controls_panel)
        layout.addWidget(self.progress)
        layout.addLayout(self.time_layout)
        layout.addWidget(self.turntable)
        layout.addWidget(self.sync_button)
        
        # Add loop controls panel
        loop_panel = QWidget()
        loop_panel.setObjectName("glassPanel")
        loop_layout = QHBoxLayout(loop_panel)
        loop_layout.setSpacing(10)
        
        loop_label = QLabel("Loop:")
        loop_label.setProperty("class", "neonText")
        loop_layout.addWidget(loop_label)
        
        # Loop start input
        start_layout = QVBoxLayout()
        start_label = QLabel("Start (s)")
        start_label.setProperty("class", "neonText")
        self.loop_start_input = QLineEdit("0.0")
        self.loop_start_input.setFixedWidth(60)
        self.loop_start_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loop_start_input.returnPressed.connect(self._update_loop_start)
        start_layout.addWidget(start_label)
        start_layout.addWidget(self.loop_start_input)
        loop_layout.addLayout(start_layout)
        
        # Loop length input
        length_layout = QVBoxLayout()
        length_label = QLabel("Length (s)")
        length_label.setProperty("class", "neonText")
        self.loop_length_input = QLineEdit("4.0")
        self.loop_length_input.setFixedWidth(60)
        self.loop_length_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loop_length_input.returnPressed.connect(self._update_loop_length)
        length_layout.addWidget(length_label)
        length_layout.addWidget(self.loop_length_input)
        loop_layout.addLayout(length_layout)
        
        # Loop toggle button
        self.loop_button = QPushButton("Loop")
        self.loop_button.setCheckable(True)
        self.loop_button.setProperty("class", "neonBorder")
        self.loop_button.clicked.connect(self.toggle_loop)
        loop_layout.addWidget(self.loop_button)
        
        layout.addWidget(loop_panel)  # Add loop panel here
        layout.addWidget(self.turntable)
        layout.addWidget(self.sync_button)
        
        layout.setStretchFactor(self.turntable, 1)
        self.turntable.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        
    def _update_bpm_display(self, bpm):
        """
        Update the BPM display and track label.

        Args:
            bpm (int): The BPM value to display.
        """
        if bpm and bpm > 0:
            self.original_bpm = int(bpm)
            self.current_bpm = int(bpm)
            self.tempo_text.setText(str(self.current_bpm))
            display_name = get_display_filename(self.current_file)
            self.track_label.setText(f"{display_name}\nBPM: {self.current_bpm}")
            print(f"\nDeck {self.deck_number} - Detected BPM: {self.current_bpm}")
        else:
            self.original_bpm = 0
            self.current_bpm = 0
            self.tempo_text.setText("---")
            display_name = get_display_filename(self.current_file)
            self.track_label.setText(display_name)
            print(f"\nDeck {self.deck_number} - No BPM detected")

    def load_file(self, file_path=None):
        """
        Load an audio file into the deck, stopping current playback and preparing for analysis and playback.

        Args:
            file_path (str, optional): Path to the audio file. If None, opens a file dialog.

        Returns:
            bool: True if loading initiated, False otherwise.
        """
        try:
            # First stop any current playback and clear the source
            self.player.stop()
            self.player.setSource(QUrl())  # Clear current source
            # Add a small delay to ensure media is cleared
            QTimer.singleShot(50, lambda: self._continue_load_file(file_path))
            return True
        except Exception as e:
            print(f"Critical error in load_file: {str(e)}"); traceback.print_exc()
            self._cleanup_temp_file()
            QMessageBox.critical(self, "Critical Error", f"A critical error occurred:\n{str(e)}")
            return False

    def _continue_load_file(self, file_path=None):
        """
        Continue loading the audio file after stopping playback and clearing the source.

        Args:
            file_path (str, optional): Path to the audio file.

        Returns:
            bool: True if loading succeeded, False otherwise.
        """
        try:
            # Clean up all temporary files and buffers
            self._cleanup_temp_file()
            
            # Reset EQ state
            if hasattr(self, 'equalizer'):
                self.equalizer.reset_transitions()
            
            file_name = file_path
            if not file_name:
                file_name, _ = QFileDialog.getOpenFileName(self, "Load Audio File", "", "Audio Files (*.mp3 *.wav *.flac *.ogg *.m4a)")
            
            if file_name:
                file_name = os.path.normpath(file_name)
                if not os.path.exists(file_name):
                    QMessageBox.warning(self, "File Error", f"File not found:\n{file_name}")
                    return False

                self.current_file = file_name
                self.original_file_path = file_name  # Save the original file path
                self.track_label.setText("Analyzing BPM...")
                
                try:
                    self._reset_eq()
                    
                    print(f"Loading track: {file_name}")
                    
                    # Try to get cached BPM and beat positions first
                    bpm = 0
                    self.beat_positions = []
                    
                    try:
                        # Check if we have cached data
                        if hasattr(self.main_app, 'cache_manager') and self.main_app.cache_manager:
                            cached_bpm, cached_beats = self.main_app.cache_manager.get_bpm_data(file_name)
                            if cached_bpm is not None and cached_bpm > 0:
                                bpm = cached_bpm
                                print(f"Using cached BPM: {bpm}")
                            
                            if cached_beats is not None and len(cached_beats) > 0:
                                self.beat_positions = cached_beats
                                print(f"Using cached beat positions: {len(self.beat_positions)} beats")
                        
                        # If we don't have cached data, analyze the file
                        if bpm == 0 or not self.beat_positions:
                            print(f"Analyzing BPM for: {file_name}")
                            try:
                                # Get BPM from regular analysis (30 seconds)
                                bpm, _ = self.main_app.audio_analyzer.analyze_file(file_name)
                            except Exception as bpm_error:
                                print(f"BPM analysis failed: {bpm_error}"); bpm = 0
                            try:
                                # Always get full track beat positions (entire song)
                                full_beats = self.main_app.audio_analyzer.get_full_track_beat_positions_ms(file_name)
                                if full_beats:
                                    self.beat_positions = full_beats
                                print(f"Detected BPM: {bpm}, {len(self.beat_positions)} beats (full track)")
                            except Exception as beat_error:
                                print(f"Full track beat analysis failed: {beat_error}")
                                if not self.beat_positions:
                                    self.beat_positions = []
                        else:
                            print(f"Using cached data - BPM: {bpm}, {len(self.beat_positions)} beats")
                            # Upgrade cached beats to full-track if available
                            try:
                                full_beats = self.main_app.audio_analyzer.get_full_track_beat_positions_ms(file_name)
                                if full_beats and len(full_beats) > len(self.beat_positions):
                                    self.beat_positions = full_beats
                                    print(f"Upgraded to full-track beats: {len(self.beat_positions)} beats")
                            except Exception as beat_error:
                                print(f"Full track beat analysis failed: {beat_error}")
                            
                    except Exception as bpm_error:
                        print(f"BPM analysis failed: {bpm_error}"); bpm = 0; self.beat_positions = []
                    
                    self._update_bpm_display(bpm)
                    if self.beat_positions: print(f"First few beats at: {self.beat_positions[:5]} ms")
                    
                    print(f"Loading high-quality audio for playback")
                    try:
                        audio_data, sample_rate = self.main_app.audio_analyzer.load_audio_for_playback(file_name)
                    except Exception as audio_error:
                        print(f"Error loading audio data: {audio_error}"); audio_data = None; sample_rate = None
                    
                    if audio_data is not None and sample_rate > 0:
                        # Set file path for caching before setting waveform data
                        self.waveform.set_current_file_path_waveform(file_name)
                        self.spectrogram.set_current_file_path_spectrogram(file_name)
                        
                        self.waveform.set_waveform_data(audio_data, sample_rate, self.beat_positions)
                        self.spectrogram.set_spectrum_data(audio_data, sample_rate)
                        
                        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_audio")
                        os.makedirs(temp_dir, exist_ok=True)
                        temp_filename = f"deck{self.deck_number}_temp_{int(time.time())}.wav"
                        self.temp_file = os.path.abspath(os.path.join(temp_dir, temp_filename))
                        
                        print(f"Creating temporary WAV file: {self.temp_file}")
                        sf.write(self.temp_file, audio_data, sample_rate)
                        if not os.path.exists(self.temp_file): raise RuntimeError(f"Failed to create temporary file: {self.temp_file}")
                        
                        source_url = QUrl.fromLocalFile(self.temp_file)
                        self.player.setSource(source_url)
                        QTimer.singleShot(35, self._check_media_loaded)
                        
                        try:
                            if audio_data is not None and sample_rate > 0:
                                self._eq_buffer = audio_data.copy(); self._eq_buffer_rate = sample_rate
                                print(f"Stored audio buffer for EQ processing: {self._eq_buffer.shape}")
                        except Exception as e: print(f"Failed to store EQ buffer: {e}")
                        return True
                    else:
                        print("Attempting to load file directly...")
                        self.player.setSource(QUrl.fromLocalFile(file_name))
                        QTimer.singleShot(35, self._check_media_loaded)
                        return True
                except Exception as e:
                    print(f"Error loading file: {str(e)}"); traceback.print_exc()
                    self._cleanup_temp_file()
                    QMessageBox.warning(self, "Load Error", f"Error loading file:\n{str(e)}")
                    return False
            return False
        except Exception as e:
            print(f"Critical error in _continue_load_file: {str(e)}"); traceback.print_exc()
            self._cleanup_temp_file()
            QMessageBox.critical(self, "Critical Error", f"A critical error occurred:\n{str(e)}")
            return False

    def _check_media_loaded(self):
        """
        Check the media status after loading and handle errors or retries.
        """
        status = self.player.mediaStatus()
        print(f"Media status check for Deck {self.deck_number}: {status}")
        if status in [QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia]:
            print(f"Deck {self.deck_number}: Media loaded successfully")
            self.update_duration(self.player.duration())
            if not self.position_timer.isActive(): self.position_timer.start()
            self.force_visualization_update()
            self._load_retries = 0 # Reset retries on success
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            error_string = self.player.errorString()
            print(f"Deck {self.deck_number}: Media load error - InvalidMedia: {error_string}")
            QMessageBox.warning(self, "Media Load Error", f"Failed to load audio (Invalid Media):\n{error_string}")
            self._cleanup_temp_file()
        elif status in [QMediaPlayer.MediaStatus.LoadingMedia, QMediaPlayer.MediaStatus.StalledMedia, QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.NoMedia]:
            print(f"Deck {self.deck_number}: Media still loading or no media (status: {status}), checking again...")
            QTimer.singleShot(100, self._check_media_loaded)
        else: # UnknownError, EndOfMedia (if trying to check after it ended before play)
            self._load_retries += 1
            if self._load_retries < 5:
                print(f"Deck {self.deck_number}: Media status {status}, retrying... (attempt {self._load_retries})")
                QTimer.singleShot(200 * self._load_retries, self._check_media_loaded) # Increasing delay
            else:
                if self.player.duration() <= 0: # Still no duration after retries
                    print(f"Deck {self.deck_number}: Failed to load media after multiple attempts (status {status})")
                    QMessageBox.warning(self, "Media Load Error", "Failed to load audio after multiple attempts.")
                    self._cleanup_temp_file()
                self._load_retries = 0 # Reset after max retries

    def force_visualization_update(self):
        """
        Force an immediate update of the visualization.
        """
        if not self.waveform or not self.player:
            return
            
        try:
            position = 0
            duration = 0
            
            # For QMediaPlayer
            if self.player and self.player.mediaStatus() in [
                QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.BufferedMedia,
                QMediaPlayer.MediaStatus.EndOfMedia
            ]:
                position = self.player.position()
                duration = self.player.duration()
            
            if duration > 0:
                print(f"Force updating waveform position for Deck {self.deck_number}: pos={position}, dur={duration}")
                self.waveform.set_position(position, duration)
                
        except Exception as e:
            print(f"Error in force_visualization_update for Deck {self.deck_number}: {e}")
            import traceback
            traceback.print_exc()

    def _cleanup_temp_file(self):
        """
        Clean up temporary files used for playback, EQ, or tempo processing.
        """
        try:
            # Clean up the main temp file
            if hasattr(self, 'temp_file') and self.temp_file and os.path.exists(self.temp_file):
                try:
                    os.remove(self.temp_file)
                    print(f"Deck {self.deck_number}: Removed temp file: {os.path.basename(self.temp_file)}")
                except Exception as e:
                    print(f"Deck {self.deck_number}: Could not remove temp file: {e}")
            
            # Clean up any EQ-processed files
            if self._last_eq_output_file:
                try:
                    if os.path.exists(self._last_eq_output_file):
                        os.remove(self._last_eq_output_file)
                        print(f"Deck {self.deck_number}: Removed last EQ file: {os.path.basename(self._last_eq_output_file)}")
                except Exception as e:
                    print(f"Deck {self.deck_number}: Could not remove last EQ file: {e}")
            
            # Reset file paths and buffers
            self.temp_file = None
            self._last_eq_output_file = None
            self._eq_buffer = None
            self._eq_buffer_rate = None
        except Exception as e:
            print(f"Deck {self.deck_number}: Error in cleanup: {e}")

    def _position_timer_tick(self):
        """
        Update UI and waveform/spectrogram position based on playback timer.
        """
        if self.is_playing:
            try:
                current_timestamp = time.time() * 1000
                position = self.player.position()
                duration = self.player.duration()
                
                # Check for loop condition
                if self._loop_enabled and position >= self._loop_end_time:
                    self.player.setPosition(self._loop_start_time)
                    position = self._loop_start_time
                
                if position >= 0 and duration > 0:
                    if not self.progress.isSliderDown() and current_timestamp - self._last_ui_update >= self._ui_update_interval:
                        self.progress.setValue(int((position / duration) * 1000))
                        current_s = position / 1000
                        self.current_time.setText(f"{int(current_s // 60)}:{int(current_s % 60):02d}")
                        self._last_ui_update = current_timestamp
                    if current_timestamp - self._last_position_update >= self._position_update_interval:
                        self.waveform.set_position(position, duration, self.beat_positions)
                        self.spectrogram.update_position(position, duration)
                        self._last_position_update = current_timestamp
            except Exception as e:
                print(f"Deck {self.deck_number}: Error in position timer update: {e}")
                if "read-only" in str(e).lower(): 
                    print(f"Deck {self.deck_number}: Detected read-only error, stopping playback")
                    self.player.stop()
                    if hasattr(self, 'position_timer') and self.position_timer.isActive():
                        self.position_timer.stop()

    def toggle_playback(self):
        """
        Toggle playback state (play/pause) for the current track.
        """
        if not self.current_file: 
            QMessageBox.information(self, "Playback Error", f"Deck {self.deck_number}: No file loaded to play/pause"); return
        try:
            if self.is_playing:
                self.player.pause() 
            else:
                # Ensure media is loaded before trying to play, especially if at end of track
                if self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia:
                    self.player.setPosition(0) # Rewind if at end
                self.player.play()  
                if not self.position_timer.isActive(): self.position_timer.start()
        except Exception as e: 
            print(f"Deck {self.deck_number}: Error in toggle_playback: {e}")

    def find_closest_beat(self, current_position_ms: int) -> tuple[int | None, int | None]:
        """
        Find the closest beat to the given position in milliseconds.

        Args:
            current_position_ms (int): Current playback position in milliseconds.

        Returns:
            tuple[int | None, int | None]: (Last beat time in ms, index of last beat) or (None, None) if not found.
        """
        if not self.beat_positions or current_position_ms < 0: return None, None
        # Handle case where current_position_ms is before the first beat
        if current_position_ms < self.beat_positions[0]: return self.beat_positions[0], 0
        
        last_beat_time = None; last_beat_idx = None
        for i, beat_time in enumerate(self.beat_positions):
            if beat_time <= current_position_ms: 
                last_beat_time = beat_time
                last_beat_idx = i
            else: # Found the first beat after current_position_ms
                break 
        # If loop finishes, last_beat_time is the last beat in the list (or None if list was empty, covered by first check)
        return last_beat_time, last_beat_idx
        
    def seek(self, value):
        """
        Seek to a position in the track based on slider value.

        Args:
            value (int): Slider value (0-1000).
        """
        if self.player.duration() > 0:
            position = (value / 1000.0) * self.player.duration()
            self.player.setPosition(int(position))
            # Immediate UI update on seek for responsiveness
            self.update_position(int(position)) 
            
    def update_position(self, position):
        """
        Update the UI and waveform/spectrogram to reflect the current playback position.

        Args:
            position (int): Current playback position in milliseconds.
        """
        duration = self.player.duration()
        if duration > 0:
            if not self.progress.isSliderDown(): 
                self.progress.setValue(int((position / duration) * 1000))
        current_s = position / 1000
        self.current_time.setText(f"{int(current_s // 60)}:{int(current_s % 60):02d}")
        self.waveform.set_position(position, duration, self.beat_positions)
        self.spectrogram.update_position(position, duration)
        
    def update_duration(self, duration):
        """
        Update the total duration label for the track.

        Args:
            duration (int): Duration in milliseconds.
        """
        if duration > 0:
            total_s = duration / 1000
            self.total_time.setText(f"{int(total_s // 60)}:{int(total_s % 60):02d}")
        else:
            self.total_time.setText("0:00")

    def handle_player_error(self, error: QMediaPlayer.Error):
        """
        Handle errors from the QMediaPlayer and display appropriate messages.

        Args:
            error (QMediaPlayer.Error): The error code from the player.
        """
        error_string = self.player.errorString()
        error_name = error.name if hasattr(error, 'name') else str(error) 
        print(f"Deck {self.deck_number} Error: {error_name} - {error_string}")
        msg = f"Media Error (Deck {self.deck_number}): {error_string}"
        if error == QMediaPlayer.Error.FormatError or error == QMediaPlayer.Error.ResourceError:
            msg += "\n\nThis may be due to an unsupported format or a corrupted file."
            try: 
                source_path = self.player.source().toLocalFile()
                if source_path: msg += f"\nProblem file: {safe_filename_for_logging(source_path)}"
            except: pass # Ignore if source cannot be read
        QMessageBox.warning(self, "Playback Error", msg)

    def adjust_position_from_turntable(self, angle_fraction):
        """
        Adjust playback position based on turntable angle.

        Args:
            angle_fraction (float): Fractional position from the turntable.
        """
        duration = self.player.duration()
        if not duration > 0: return
        try:
            new_pos = int(duration * angle_fraction)
            new_pos = max(0, min(new_pos, duration))
            
            was_playing = (self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
            if was_playing: self.player.pause() 
            self.player.setPosition(new_pos)
            self.update_position(new_pos) # Immediate UI update
            if was_playing: QTimer.singleShot(20, self.player.play)
        except Exception as e:
            print(f"Deck {self.deck_number}: Error in turntable seek: {e}")
            if "stream" in str(e).lower(): self._recover_from_stream_error()
                
    def _recover_from_stream_error(self):
        """
        Attempt to recover from a stream error by reloading the current file.
        """
        print(f"Deck {self.deck_number}: Attempting to recover from stream error.")
        try:
            was_playing = self.is_playing # Use the property which reflects actual state
            position = self.player.position()
            self.player.stop() 

            # Attempt to reload the current temp_file if it exists
            file_to_reload = self.temp_file if (self.temp_file and os.path.exists(self.temp_file)) else self.current_file
            
            if file_to_reload and os.path.exists(file_to_reload):
                print(f"Deck {self.deck_number}: Reloading source: {file_to_reload}")
                self.player.setSource(QUrl.fromLocalFile(file_to_reload))
                # Media status check before setting position
                QTimer.singleShot(100, lambda: self._finalize_recovery(position, was_playing))
            else:
                print(f"Deck {self.deck_number}: No valid file to recover with.")
                self.handle_player_error(QMediaPlayer.Error.ResourceError)
        except Exception as e:
            print(f"Deck {self.deck_number}: Critical error during stream recovery: {e}")
            self.handle_player_error(QMediaPlayer.Error.ResourceError)

    def _finalize_recovery(self, position, was_playing):
        """
        Finalize recovery after a stream error, restoring position and playback state.

        Args:
            position (int): Playback position to restore.
            was_playing (bool): Whether playback was active before the error.
        """
        if self.player.mediaStatus() in [QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia]:
            self.player.setPosition(position)
            if was_playing: 
                self.player.play()
            print(f"Deck {self.deck_number}: Stream recovery successful.")
        else:
            print(f"Deck {self.deck_number}: Media not loaded after recovery attempt. Status: {self.player.mediaStatus()}")
            self.handle_player_error(QMediaPlayer.Error.ResourceError) 

    def _update_turntable_state(self, state: QMediaPlayer.PlaybackState):
        """
        Update the turntable state and UI based on playback state changes.

        Args:
            state (QMediaPlayer.PlaybackState): The new playback state.
        """
        current_is_playing = (state == QMediaPlayer.PlaybackState.PlayingState)
        if self._is_playing != current_is_playing:
            self.is_playing = current_is_playing 
        
        state_map = { QMediaPlayer.PlaybackState.StoppedState: 'Stopped', QMediaPlayer.PlaybackState.PlayingState: 'Playing', QMediaPlayer.PlaybackState.PausedState: 'Paused' }
        print(f"---> Deck {self.deck_number}: Playback state changed to: {state_map.get(state, state.value if hasattr(state, 'value') else state)}")
        self.turntable.set_playing(current_is_playing)
        
        duration = self.player.duration()
        if state == QMediaPlayer.PlaybackState.StoppedState and duration > 0 and self.player.position() >= duration:
            print(f"Deck {self.deck_number}: End of media reached.")
            self.player.setPosition(0) 
            if self.is_playing: self.player.pause() 
            self.update_position(0)

    def adjust_tempo(self, change):
        """
        Adjust the deck's tempo (BPM) by a given amount.

        Args:
            change (int): Amount to change the BPM by.
        """
        if self.original_bpm == 0: 
            print(f"Deck {self.deck_number}: Cannot adjust tempo - Original BPM not set."); return
        new_bpm = max(20, min(self.current_bpm + change, 300))
        if new_bpm != self.current_bpm:
            print(f"Deck {self.deck_number}: Requesting tempo change from {self.current_bpm} to {new_bpm} BPM")
            if self.main_app and hasattr(self.main_app, 'sync_master') and self.main_app.sync_master == self.deck_number:
                 if hasattr(self.main_app, 'sync_slave_deck_tempo'):
                    self.main_app.sync_slave_deck_tempo(new_bpm)
            self.set_deck_tempo(new_bpm)

    def reset_tempo(self):
        """
        Reset the deck's tempo to the original BPM.
        """
        if self.original_bpm == 0: 
            print(f"Deck {self.deck_number}: Cannot reset tempo - Original BPM not set."); return
        if self.current_bpm != self.original_bpm:
            print(f"Deck {self.deck_number}: Requesting tempo reset to {self.original_bpm} BPM")
            if self.main_app and hasattr(self.main_app, 'sync_master') and self.main_app.sync_master == self.deck_number:
                 if hasattr(self.main_app, 'sync_slave_deck_tempo'):
                    self.main_app.sync_slave_deck_tempo(self.original_bpm)
            self.set_deck_tempo(self.original_bpm)
        else: 
            print(f"Deck {self.deck_number}: Tempo already at original {self.current_bpm} BPM.")

    def set_deck_tempo(self, new_bpm, target_position_after_load=None):
        """
        Set the deck's tempo to a new BPM, processing the audio as needed.

        Args:
            new_bpm (int): The new BPM to set.
            target_position_after_load (int, optional): Position to seek to after loading.
        """
        if self.original_bpm <= 0: 
            print(f"Deck {self.deck_number}: Original BPM unknown, cannot set tempo."); return
        if not self.audio_analyzer or not self.audio_analyzer.is_available():
            QMessageBox.warning(self, "Tempo Change Failed", "Audio Analyzer unavailable."); return
        
        # Crucially, the tempo change should ALWAYS be based on the true original file
        if not self.original_file_path or not os.path.exists(self.original_file_path):
            QMessageBox.warning(self, "Tempo Change Failed", "Original audio file for this deck is missing or not loaded."); return
        
        # Store the original file path to prevent it from being overwritten
        original_file_for_processing = self.original_file_path
        
        # Get duration from the original file for an accurate basis, not player's current duration if it's already processed
        try:
            info = sf.info(original_file_for_processing)
            original_dur_ms_from_file = info.duration * 1000
            if original_dur_ms_from_file <= 0:
                print(f"Deck {self.deck_number}: Original track duration from file info is zero or invalid."); return
        except Exception as e_info:
            print(f"Deck {self.deck_number}: Could not get duration from original file info: {e_info}. Player duration: {self.player.duration()}")
            # Fallback to player duration if info fails, but this might be from a processed file
            original_dur_ms_from_file = self.player.duration()
            if original_dur_ms_from_file <= 0:
                print(f"Deck {self.deck_number}: Track duration unknown after fallback."); return

        # Calculate stretch factor for FFT time stretching:
        # The correct mathematical relationship:
        #   - stretchFactor > 1.0 results in SLOWER playback (longer duration).
        #   - stretchFactor < 1.0 results in FASTER playback (shorter duration).
        # To achieve desired DJ deck behavior:
        #   - If new_bpm > original_bpm (faster playback desired), we need stretchFactor < 1.0.
        #   - If new_bpm < original_bpm (slower playback desired), we need stretchFactor > 1.0.
        # The calculation original_bpm / new_bpm provides the correct factor for this behavior.
        stretch_factor = self.original_bpm / new_bpm
        if not (0.25 <= stretch_factor <= 4.0): # SoundStretch limits
            QMessageBox.warning(self, "Tempo Change Failed", f"Requested BPM {new_bpm} (factor {stretch_factor:.2f}) is out of reasonable range for original {self.original_bpm}."); return

        # current_pos_ms should be relative to the current playback, which might be of a processed file.
        # We need to map this position back to the original file's timeline if possible, or use fraction.
        current_player_pos_ms = self.player.position()
        current_player_dur_ms = self.player.duration() # Duration of currently playing media
        pos_fraction = current_player_pos_ms / current_player_dur_ms if current_player_dur_ms > 0 else 0
        
        was_playing = (self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        
        # Calculate target position for worker based on the *original* file's duration
        if target_position_after_load is None:
            target_pos_for_worker = int(pos_fraction * original_dur_ms_from_file * stretch_factor)
            # Ensure target is within new stretched duration of the original file
            new_stretched_original_duration = original_dur_ms_from_file * stretch_factor
            target_pos_for_worker = max(0, min(target_pos_for_worker, int(new_stretched_original_duration)))
        else:
            target_pos_for_worker = target_position_after_load # Use provided if available (e.g., for beat sync)

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_tempo")
        try:
            os.makedirs(temp_dir, exist_ok=True)
            # Create ASCII-safe filename to avoid encoding issues with Hebrew/Unicode characters
            original_name = os.path.splitext(os.path.basename(original_file_for_processing))[0]
            # Only keep ASCII alphanumeric characters, spaces, underscores, and hyphens
            safe_base = "".join(c for c in original_name if c.isascii() and (c.isalnum() or c in (' ', '_', '-'))).strip()
            # If no safe characters remain, use a generic identifier
            if not safe_base:
                safe_base = "track"
            # More unique filename for temp tempo file with ASCII-safe name
            temp_output_file = os.path.join(temp_dir, f"deck{self.deck_number}_{safe_base[:20]}_{int(time.time()*1000)}_{new_bpm}bpm.wav")
            
            # Cleanup old *tempo* files for THIS deck
            for f_name in os.listdir(temp_dir):
                if f_name.startswith(f"deck{self.deck_number}_") and f_name.endswith(".wav") and f_name != os.path.basename(temp_output_file):
                    try:
                         os.remove(os.path.join(temp_dir, f_name))
                         print(f"Deck {self.deck_number}: Cleaned old tempo file: {f_name}") 
                    except OSError as e_del: print(f"Deck {self.deck_number}: Could not clean old tempo file {f_name}: {e_del}")
        except Exception as e:
            print(f"Deck {self.deck_number}: Error creating temp dir/filename for tempo: {e}")
            QApplication.restoreOverrideCursor()
            return

        try:
            if was_playing: self.player.pause()
            
            # Pass the original file path and its true duration in seconds for processing
            self.tempo_worker = TempoChangeWorker(self.deck_number, self.audio_analyzer, original_file_for_processing, temp_output_file, stretch_factor, original_dur_ms_from_file / 1000.0, new_bpm, target_pos_for_worker, was_playing)
            self.tempo_worker.finished.connect(self._handle_tempo_change_finished)
            self.tempo_worker.error.connect(self._handle_tempo_change_error)
            self.tempo_worker.start()
            self.tempoProcessing.emit(True)
            self.set_controls_enabled(False)
        except Exception as e: 
            print(f"Deck {self.deck_number}: Exception starting tempo worker: {e}")
            QMessageBox.critical(self, "Tempo Error", f"Error processing tempo: {e}")
            self.tempo_worker = None
            self.set_controls_enabled(True)
            self.tempoProcessing.emit(False)
            QApplication.restoreOverrideCursor()
            if was_playing: self.player.play()

    def _handle_tempo_change_finished(self, deck_num, temp_file_path, success, target_bpm, target_position, was_playing_flag):
        """
        Handle completion of tempo change processing.

        Args:
            deck_num (int): Deck number.
            temp_file_path (str): Path to the processed file.
            success (bool): Whether the processing succeeded.
            target_bpm (int): Target BPM.
            target_position (int): Position to seek to after loading.
            was_playing_flag (bool): Whether playback was active before processing.
        """
        if deck_num != self.deck_number: return
        QApplication.restoreOverrideCursor()
        self.set_controls_enabled(True)
        self.tempoProcessing.emit(False)
        self.tempo_worker = None

        if success and os.path.exists(temp_file_path) and os.path.getsize(temp_file_path) > 0:
             # Store the original file path to prevent it from being overwritten during processing
             preserved_original_file = self.original_file_path
             
             self.current_bpm = target_bpm 
             self.tempo_text.setText(str(self.current_bpm))
             self.track_label.setText(f"{get_display_filename(preserved_original_file)} ({self.current_bpm} BPM)")
             
             self._resume_after_load = was_playing_flag
             try:
                 audio_data, sr = sf.read(temp_file_path, dtype='float32')
                 self._eq_buffer = audio_data
                 self._eq_buffer_rate = sr
                 
                 # Scale beat positions to match the new tempo
                 # With the corrected stretch factor calculation: stretch_factor = original_bpm / new_bpm
                 # Beat positions need to be scaled by the stretch factor itself: original_bpm / new_bpm
                 if self.beat_positions and self.original_bpm > 0:
                     beat_scale_factor = self.original_bpm / target_bpm
                     scaled_beat_positions = [int(beat_ms * beat_scale_factor) for beat_ms in self.beat_positions]
                 else:
                     scaled_beat_positions = self.beat_positions
                 
                 self.waveform.set_waveform_data(audio_data, sr, scaled_beat_positions)
                 self.spectrogram.set_spectrum_data(audio_data, sr)
                 
             except Exception as e_read:
                 print(f"Deck {self.deck_number}: Failed to read new tempo file for EQ buffer and waveform: {e_read}")
                 self._eq_buffer = None
                 self._eq_buffer_rate = None

             self._cleanup_temp_file() # Clean the *previous* self.temp_file
             self.temp_file = temp_file_path # This is the new main playable file

             # Check if EQ settings are non-neutral and need to be reapplied
             eq_is_not_neutral = (abs(self._eq_bass_gain - 1.0) > 0.01 or
                                 abs(self._eq_mid_gain - 1.0) > 0.01 or
                                 abs(self._eq_treble_gain - 1.0) > 0.01)
             
             if eq_is_not_neutral:
                 print(f"Deck {self.deck_number}: Non-neutral EQ detected after tempo change - Bass: {self._eq_bass_gain:.2f}, Mid: {self._eq_mid_gain:.2f}, Treble: {self._eq_treble_gain:.2f}")
                 print(f"Deck {self.deck_number}: Will reapply EQ to tempo-processed file")
                 
                 # Store the target position and playing state for after EQ reapplication
                 self._pending_seek_position = target_position
                 self._pending_resume_playback = was_playing_flag
                 
                 # Set the source to the tempo-processed file first
                 self.player.setSource(QUrl.fromLocalFile(self.temp_file))
                 
                 # Restore the original file path reference to prevent confusion
                 self.original_file_path = preserved_original_file
                 
                 # Wait a bit for the tempo file to load, then apply EQ
                 QTimer.singleShot(150, lambda: self._reapply_eq_after_tempo_change())
             else:
                 print(f"Deck {self.deck_number}: EQ is neutral, no need to reapply after tempo change")
                 
                 # Normal flow - just load the tempo-processed file
                 self.player.setSource(QUrl.fromLocalFile(self.temp_file))
                 
                 # Restore the original file path reference to prevent confusion
                 self.original_file_path = preserved_original_file
                 
                 QTimer.singleShot(100, lambda: self._check_media_and_seek_resume(target_position))
        else:
             QMessageBox.warning(self, "Tempo Change Failed", f"Could not process audio to {target_bpm} BPM. File: {safe_filename_for_logging(temp_file_path)}")
             if was_playing_flag and self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState: self.player.play()

    def _reapply_eq_after_tempo_change(self):
        """
        Reapply current EQ settings to the tempo-processed file after tempo change.
        """
        try:
            print(f"Deck {self.deck_number}: Reapplying EQ after tempo change")
            
            # Store position info before applying EQ
            target_position = getattr(self, '_pending_seek_position', None)
            should_resume = getattr(self, '_pending_resume_playback', False)
            
            print(f"Deck {self.deck_number}: Preserved position for EQ reapplication: {target_position}ms, Resume: {should_resume}")
            
            # Clear the pending attributes
            if hasattr(self, '_pending_seek_position'):
                delattr(self, '_pending_seek_position')
            if hasattr(self, '_pending_resume_playback'):
                delattr(self, '_pending_resume_playback')
            
            # Apply EQ to the current tempo-processed file, passing the target position
            self._apply_eq(reset_transitions=False, target_position_after_eq=target_position, resume_after_eq=should_resume)
            
        except Exception as e:
            print(f"Deck {self.deck_number}: Error reapplying EQ after tempo change: {e}")
            # Fallback to normal tempo completion
            target_position = getattr(self, '_pending_seek_position', None)
            should_resume = getattr(self, '_pending_resume_playback', False)
            QTimer.singleShot(100, lambda: self._check_media_and_seek_resume(target_position, should_resume))

    def _check_media_and_seek_resume(self, target_position, should_resume=None):
        """
        Check if media is loaded and seek/resume playback after tempo change.

        Args:
            target_position (int): Position to seek to after loading.
            should_resume (bool, optional): Override for resume playback state.
        """
        # Use the override if provided, otherwise use the stored state
        resume_playback = should_resume if should_resume is not None else self._resume_after_load
        
        status = self.player.mediaStatus()
        if status == QMediaPlayer.MediaStatus.LoadedMedia or status == QMediaPlayer.MediaStatus.BufferedMedia:
            new_duration = self.player.duration()
            self.update_duration(new_duration)
            
            if target_position is not None and new_duration > 0:
                safe_target_pos = max(0, min(int(target_position), int(new_duration)))
                self.player.setPosition(safe_target_pos)
                self.update_position(safe_target_pos)

            if resume_playback:
                self.player.play()
            self._resume_after_load = False
        elif status in [QMediaPlayer.MediaStatus.LoadingMedia, QMediaPlayer.MediaStatus.StalledMedia, 
                           QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.NoMedia]:
            QTimer.singleShot(100, lambda: self._check_media_and_seek_resume(target_position, should_resume))
        else: 
            QMessageBox.warning(self, "Playback Error", f"Failed to load processed audio (Status: {status.value if hasattr(status, 'value') else status}).")
            self._resume_after_load = False

    def _handle_tempo_change_error(self, deck_num, error_message):
        """
        Handle errors during tempo change processing.

        Args:
            deck_num (int): Deck number.
            error_message (str): Error message.
        """
        if deck_num != self.deck_number: return
        QApplication.restoreOverrideCursor(); 
        QMessageBox.critical(self, "Tempo Change Error", f"Error processing tempo: {error_message}")
        self.tempo_worker = None; self.set_controls_enabled(True); self.tempoProcessing.emit(False)
        if self._resume_after_load and self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
             self.player.play()
        self._resume_after_load = False

    def set_controls_enabled(self, enabled):
        """
        Enable or disable all deck controls.

        Args:
            enabled (bool): Whether to enable or disable controls.
        """
        self.play_btn.setEnabled(enabled)
        self.volume_slider.setEnabled(enabled)
        if self.tempo_text and isinstance(self.tempo_text.parentWidget(), QWidget):
            self.tempo_text.parentWidget().setEnabled(enabled)
        self.progress.setEnabled(enabled)
        self.turntable.setEnabled(enabled)
        if self.sync_button:
            self.sync_button.setEnabled(enabled)
        self.bass_knob.setEnabled(enabled)
        self.mid_knob.setEnabled(enabled)
        self.treble_knob.setEnabled(enabled)
        # Add loop controls
        self.loop_button.setEnabled(enabled)
        self.loop_start_input.setEnabled(enabled)
        self.loop_length_input.setEnabled(enabled)
        if self.bass_knob and isinstance(self.bass_knob.parentWidget(), QWidget) and \
           isinstance(self.bass_knob.parentWidget().parentWidget(), QWidget):
            self.bass_knob.parentWidget().parentWidget().setEnabled(enabled)

    def handle_volume_change(self, value):
        """
        Handle changes to the volume slider.

        Args:
            value (int): Slider value (0-100).
        """
        try:
            volume = value / 100.0
            self._current_volume = volume 
            self.volumeChanged.emit()
        except Exception as e: print(f"Deck {self.deck_number}: Error in handle_volume_change: {e}"); traceback.print_exc()

    def get_current_volume(self):
        """
        Get the current volume as a float between 0.0 and 1.0.

        Returns:
            float: Current volume.
        """
        return self.volume_slider.value() / 100.0

    @property
    def is_playing(self):
        """
        bool: Whether the deck is currently playing.
        """
        return self._is_playing
    @is_playing.setter
    def is_playing(self, value):
        """
        Set the playing state and update the play button text.

        Args:
            value (bool): Playing state.
        """
        changed = self._is_playing != value
        self._is_playing = value
        if changed and hasattr(self, 'play_btn'): 
            self.play_btn.setText("Pause" if value else "Play")



    def adjust_playback_rate(self, pitch_percent):
        """
        Adjust the playback rate based on pitch percent.

        Args:
            pitch_percent (float): Pitch adjustment in percent.
        """
        try:
            rate = max(0.5, min(1.0 + (pitch_percent / 100.0), 2.0))
            self.player.setPlaybackRate(rate)
        except Exception as e: print(f"Deck {self.deck_number}: Error adjusting playback rate: {e}"); traceback.print_exc()

    def handle_bpm_input(self):
        """
        Handle BPM input from the user and trigger tempo change if valid.
        """
        if not self.original_file_path or self.original_bpm <= 0:
            self.tempo_text.setText(str(self.current_bpm) if self.current_bpm > 0 else "---"); return
        try:
            new_bpm = int(self.tempo_text.text())
            if not (20 <= new_bpm <= 300):
                QMessageBox.warning(self, "Invalid BPM", "BPM must be between 20 and 300.")
                self.tempo_text.setText(str(self.current_bpm)); return
            if new_bpm == self.current_bpm: return
            print(f"Deck {self.deck_number}: BPM entered via text: {new_bpm}")
            if self.main_app and hasattr(self.main_app, 'sync_master') and self.main_app.sync_master == self.deck_number:
                if hasattr(self.main_app, 'sync_slave_deck_tempo'):
                    self.main_app.sync_slave_deck_tempo(new_bpm)
            self.set_deck_tempo(new_bpm)
        except ValueError: 
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid number for BPM.")
            self.tempo_text.setText(str(self.current_bpm))
        except Exception as e: 
            print(f"Deck {self.deck_number}: Error handling BPM input: {e}"); self.tempo_text.setText(str(self.current_bpm))

    def _on_eq_changed(self):
        """
        Handle EQ knob changes with debounced processing.
        """
        # Update internal gain values (0-200 -> 0.0-2.0)
        self._eq_bass_gain = self.bass_knob.value() / 100.0
        self._eq_mid_gain = self.mid_knob.value() / 100.0
        self._eq_treble_gain = self.treble_knob.value() / 100.0
        
        # Check if EQ is at neutral position (all knobs at 1.0)
        eq_is_neutral = (abs(self._eq_bass_gain - 1.0) < 0.01 and 
                        abs(self._eq_mid_gain - 1.0) < 0.01 and 
                        abs(self._eq_treble_gain - 1.0) < 0.01)
        
        # Provide immediate visual feedback
        print(f"Deck {self.deck_number}: EQ changed - Bass: {self._eq_bass_gain:.2f}, Mid: {self._eq_mid_gain:.2f}, Treble: {self._eq_treble_gain:.2f}")
        
        # Update spectrogram EQ overlay immediately for visual feedback
        try:
            self.spectrogram.update_eq_gains(self._eq_bass_gain, self._eq_mid_gain, self._eq_treble_gain)
        except Exception as e:
            print(f"Deck {self.deck_number}: Error updating spectrogram EQ overlay: {e}")
        
        # Cancel any existing EQ timer
        if hasattr(self, '_eq_timer') and self._eq_timer.isActive():
            self._eq_timer.stop()
        
        # Create or restart timer for debounced EQ processing
        if not hasattr(self, '_eq_timer'):
            self._eq_timer = QTimer()
            self._eq_timer.setSingleShot(True)
            self._eq_timer.timeout.connect(lambda: self._apply_eq(reset_transitions=False))
        
        # Set a short delay to avoid processing on every tiny knob movement
        self._eq_timer.start(800)  # 800ms delay for better responsiveness
        
        # Show immediate status update
        if hasattr(self, 'eq_status_label'):
            if eq_is_neutral:
                self.eq_status_label.setText("EQ Neutral")
                QTimer.singleShot(1000, lambda: self.eq_status_label.setVisible(False))
            else:
                self.eq_status_label.setText("EQ Pending...")
                self.eq_status_label.setVisible(True)


    def _reset_eq(self):
        """
        Reset EQ knobs to neutral position and apply neutral EQ processing.
        
        Sets all EQ knobs back to their neutral position (100 = 1.0 gain)
        and forces the application of neutral EQ to actually reset the audio.
        """
        print(f"Deck {self.deck_number}: Resetting EQ knobs to neutral")
        
        # Set knob values to neutral (100 = 1.0 gain)
        self.bass_knob.setValue(100)
        self.mid_knob.setValue(100)
        self.treble_knob.setValue(100)
        
        # Update internal gain values
        self._eq_bass_gain = 1.0
        self._eq_mid_gain = 1.0
        self._eq_treble_gain = 1.0
        
        # Reset EQ transitions in the Python equalizer
        if hasattr(self, 'equalizer'):
            self.equalizer.reset_transitions()
        
        # Force application of neutral EQ to actually reset the audio
        print(f"Deck {self.deck_number}: Applying neutral EQ to reset audio")
        self._force_apply_neutral_eq()
        
        print(f"Deck {self.deck_number}: EQ reset completed")

    def _force_apply_neutral_eq(self):
        """
        Force application of neutral EQ settings to reset audio to its base state.
        """
        if not self.original_file_path or not os.path.exists(self.original_file_path):
            print(f"Deck {self.deck_number}: No original file available for EQ reset")
            return

        # IMPORTANT: Capture the current position FIRST before any processing
        # Get current playback state immediately to avoid position drift
        was_playing = (self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        current_pos = self.player.position()
        duration = self.player.duration()
        
        # Calculate actual time elapsed in seconds
        time_elapsed_seconds = current_pos / 1000.0 if current_pos > 0 else 0.0
        
        # Validation: If we have almost no elapsed time but duration exists, something is wrong
        if time_elapsed_seconds < 0.1 and duration > 1000:
            print(f"Deck {self.deck_number}: WARNING - Very small elapsed time ({time_elapsed_seconds:.2f}s) with duration {duration}ms, position may not be valid")
        
        print(f"Deck {self.deck_number}: CAPTURED - Position: {current_pos}ms, Duration: {duration}ms, Time elapsed: {time_elapsed_seconds:.2f}s, Playing: {was_playing}")

        # Don't proceed if we don't have valid position info and the track should have position
        if current_pos <= 0 and duration > 1000:
            print(f"Deck {self.deck_number}: WARNING - Position is 0 but duration is {duration}ms. This may cause restart issue.")
        
        # Pause immediately to prevent position from changing during processing
        if was_playing:
            self.player.pause()
            print(f"Deck {self.deck_number}: Paused playback for EQ reset processing")

        try:
            # Clean up previous EQ file first
            if self._last_eq_output_file and os.path.exists(self._last_eq_output_file):
                try:
                    os.remove(self._last_eq_output_file)
                    print(f"Deck {self.deck_number}: Cleaned up previous EQ file")
                except:
                    pass
                self._last_eq_output_file = None

            # Determine what file we need based on current BPM state
            if self.current_bpm != self.original_bpm and self.original_bpm > 0:
                # BPM has been changed - we need a tempo-processed file
                print(f"Deck {self.deck_number}: BPM changed ({self.original_bpm} -> {self.current_bpm}), creating tempo-only file for EQ reset")
                
                # Clean up old temp file if it exists
                if self.temp_file and os.path.exists(self.temp_file):
                    try:
                        os.remove(self.temp_file)
                        print(f"Deck {self.deck_number}: Cleaned up old temp file")
                    except:
                        pass
                
                # Create a fresh tempo-processed file for the current BPM
                temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_tempo")
                os.makedirs(temp_dir, exist_ok=True)
                
                tempo_file = os.path.join(temp_dir, f"deck{self.deck_number}_tempo_reset_{int(time.time()*1000)}.wav")
                
                # Calculate stretch factor
                stretch_factor = self.original_bpm / self.current_bpm
                
                print(f"Deck {self.deck_number}: Creating tempo file with factor {stretch_factor:.3f}")
                
                # Create tempo-processed file using the analyzer
                if hasattr(self, 'audio_analyzer') and self.audio_analyzer and self.audio_analyzer.is_available():
                    # Read original file to get length
                    try:
                        original_audio, sample_rate = sf.read(self.original_file_path, dtype='float32')
                        length_seconds = len(original_audio) / sample_rate
                        
                        success = self.audio_analyzer.change_tempo(
                            self.original_file_path,
                            tempo_file,
                            stretch_factor,
                            length_seconds
                        )
                        
                        if success and os.path.exists(tempo_file) and os.path.getsize(tempo_file) > 0:
                            base_file = tempo_file
                            # Update temp_file to point to our new tempo file
                            self.temp_file = tempo_file
                            print(f"Deck {self.deck_number}: Successfully created tempo file: {os.path.basename(base_file)}")
                        else:
                            print(f"Deck {self.deck_number}: Tempo processing failed or produced empty file, using original")
                            # Clean up failed tempo file
                            if os.path.exists(tempo_file):
                                try:
                                    os.remove(tempo_file)
                                except:
                                    pass
                            base_file = self.original_file_path
                            self.temp_file = None
                    except Exception as tempo_error:
                        print(f"Deck {self.deck_number}: Error during tempo processing: {tempo_error}")
                        base_file = self.original_file_path
                        self.temp_file = None
                else:
                    print(f"Deck {self.deck_number}: BPM analyzer unavailable, using original file")
                    base_file = self.original_file_path
                    self.temp_file = None
            else:
                # No BPM change, use original file
                base_file = self.original_file_path
                # Clean up any old temp file since we're going back to original
                if self.temp_file and os.path.exists(self.temp_file):
                    try:
                        os.remove(self.temp_file)
                        print(f"Deck {self.deck_number}: Cleaned up temp file, using original")
                    except:
                        pass
                self.temp_file = None
                print(f"Deck {self.deck_number}: Using original file: {os.path.basename(base_file)}")

            # Verify the file exists before trying to load it
            if not os.path.exists(base_file):
                print(f"Deck {self.deck_number}: Error - Base file doesn't exist: {base_file}")
                return

            # Set the player to use the base file (unprocessed by EQ, but with correct tempo)
            print(f"Deck {self.deck_number}: Loading new source file: {os.path.basename(base_file)}")
            self.player.setSource(QUrl.fromLocalFile(base_file))
            
            # Update spectrogram with neutral gains
            if hasattr(self, 'spectrogram'):
                self.spectrogram.update_eq_gains(1.0, 1.0, 1.0)
            
            print(f"Deck {self.deck_number}: EQ reset applied, using file: {os.path.basename(base_file)}")
            
            # Wait a bit longer for the media to load, then restore position
            QTimer.singleShot(200, lambda: self._restore_position_and_resume_by_time(time_elapsed_seconds, was_playing))
            
        except Exception as e:
            print(f"Deck {self.deck_number}: Error applying neutral EQ: {e}")
            traceback.print_exc()
            # Try to resume playback even if there was an error
            if was_playing:
                self.player.play()

    def _restore_position_and_resume_by_time(self, time_elapsed_seconds, was_playing):
        """
        Restore playback position based on elapsed time and resume if was playing.
        
        Args:
            time_elapsed_seconds (float): Time elapsed in seconds from the start.
            was_playing (bool): Whether playback was active before reset.
        """
        try:
            print(f"Deck {self.deck_number}: Attempting to restore position to {time_elapsed_seconds:.2f}s")
            
            # Wait for media to be loaded
            status = self.player.mediaStatus()
            print(f"Deck {self.deck_number}: Media status: {status}")
            
            if status in [QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia]:
                # Get the new file duration
                new_duration = self.player.duration()
                print(f"Deck {self.deck_number}: New file duration: {new_duration}ms")
                
                # Calculate position based on elapsed time
                target_position_ms = int(time_elapsed_seconds * 1000)
                
                # Make sure position is within bounds
                if new_duration > 0:
                    target_position_ms = max(0, min(target_position_ms, new_duration - 1000))  # Leave 1 second buffer
                else:
                    target_position_ms = 0
                
                print(f"Deck {self.deck_number}: Setting position to {target_position_ms}ms (from elapsed time: {time_elapsed_seconds:.2f}s)")
                
                # Set the position
                self.player.setPosition(target_position_ms)
                
                # Update the UI position display
                self.update_position(target_position_ms)
                
                # Wait a moment for position to be set, then resume if needed
                if was_playing:
                    # Small delay to ensure position is set before resuming
                    QTimer.singleShot(50, lambda: self._resume_playback_after_position_set())
                else:
                    print(f"Deck {self.deck_number}: Position restored, playback was paused")
                    
            elif status in [QMediaPlayer.MediaStatus.LoadingMedia, QMediaPlayer.MediaStatus.StalledMedia, 
                           QMediaPlayer.MediaStatus.BufferingMedia]:
                # Media still loading, try again with backoff
                print(f"Deck {self.deck_number}: Media still loading (status: {status}), retrying position restore...")
                QTimer.singleShot(200, lambda: self._restore_position_and_resume_by_time(time_elapsed_seconds, was_playing))
            elif status == QMediaPlayer.MediaStatus.NoMedia:
                print(f"Deck {self.deck_number}: No media loaded, retrying...")
                QTimer.singleShot(300, lambda: self._restore_position_and_resume_by_time(time_elapsed_seconds, was_playing))
            else:
                print(f"Deck {self.deck_number}: Media load failed after EQ reset (status: {status})")
                
        except Exception as e: 
            print(f"Deck {self.deck_number}: Error restoring position after EQ reset: {e}")
            if was_playing:
                self.player.play()

    def _resume_playback_after_position_set(self):
        """
        Resume playback after position has been set.
        """
        try:
            current_pos = self.player.position()
            print(f"Deck {self.deck_number}: Resuming playback at position {current_pos}ms")
            self.player.play()
            print(f"Deck {self.deck_number}: Playback resumed after EQ reset")
        except Exception as e:
            print(f"Deck {self.deck_number}: Error resuming playback: {e}")

    def _apply_eq(self, reset_transitions=False, target_position_after_eq=None, resume_after_eq=None):
        """
        Apply EQ by processing audio file and loading the result.

        Args:
            reset_transitions (bool): Whether to reset EQ transitions before processing.
            target_position_after_eq (int, optional): Specific position to seek to after EQ processing.
            resume_after_eq (bool, optional): Whether to resume playback after EQ processing.
        """
        print(f"\nDeck {self.deck_number}: Applying EQ processing")
        
        # Show processing status
        if hasattr(self, 'eq_status_label'):
            self.eq_status_label.setText("Processing EQ...")
            self.eq_status_label.setVisible(True)
        
        # Check if we need to apply EQ changes
        needs_eq_change = (abs(self._eq_bass_gain - 1.0) > 0.01 or 
                          abs(self._eq_mid_gain - 1.0) > 0.01 or 
                          abs(self._eq_treble_gain - 1.0) > 0.01)
        
        if not needs_eq_change:
            print(f"Deck {self.deck_number}: EQ gains are neutral, applying base file")
            self._force_apply_neutral_eq()
            return

        if not self.original_file_path or not os.path.exists(self.original_file_path):
            print(f"Deck {self.deck_number}: No original file available for EQ processing")
            if hasattr(self, 'eq_status_label'):
                self.eq_status_label.setVisible(False)
            return

        # Get current playback state and position (unless overridden)
        if target_position_after_eq is not None and resume_after_eq is not None:
            # Use provided values (from tempo change flow)
            was_playing = resume_after_eq
            current_pos = target_position_after_eq
            duration = self.player.duration()
            pos_fraction = current_pos / duration if duration > 0 else 0
            print(f"Deck {self.deck_number}: Using provided position for EQ: {current_pos}ms, Resume: {was_playing}")
        else:
            # Normal EQ flow - capture current state
            was_playing = (self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
            current_pos = self.player.position()
            duration = self.player.duration()
            pos_fraction = current_pos / duration if duration > 0 else 0

        try:
            if reset_transitions and hasattr(self, 'equalizer'): 
                self.equalizer.reset_transitions()
            
            # Start with the appropriate base file (original or tempo-processed)
            base_file = self.original_file_path
            if self.current_bpm != self.original_bpm and self.original_bpm > 0:
                # If tempo has been changed, we need the tempo-processed file
                # For now, let's apply EQ to the current playing file
                if self.temp_file and os.path.exists(self.temp_file):
                    base_file = self.temp_file
            
            print(f"Deck {self.deck_number}: Processing EQ from: {os.path.basename(base_file)}")
            
            # Load the base audio
            audio_data, sample_rate = sf.read(base_file, dtype='float32')
            
            # Apply EQ using our Python equalizer (which calls the C++ EQ)
            if hasattr(self, 'equalizer') and self.equalizer:
                processed_audio = self.equalizer.process(
                    audio_data, 
                    sample_rate,
                    self._eq_bass_gain,
                    self._eq_mid_gain,
                    self._eq_treble_gain
                )
            else:
                # Fallback: no EQ processing
                processed_audio = audio_data
            
            if processed_audio is None or processed_audio.size == 0:
                print(f"Deck {self.deck_number}: EQ processing failed, using original")
                processed_audio = audio_data
            
            # Save the processed file
            temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_audio")
            os.makedirs(temp_dir, exist_ok=True)
            
            eq_filename = f"deck{self.deck_number}_eq_{int(time.time()*1000)}.wav"
            eq_file_path = os.path.join(temp_dir, eq_filename)
            
            sf.write(eq_file_path, processed_audio, sample_rate)
            
            if not os.path.exists(eq_file_path):
                raise IOError(f"Failed to create EQ processed file")
            
            print(f"Deck {self.deck_number}: EQ file created: {os.path.basename(eq_file_path)}")
            
            # Pause current playback
            if was_playing:
                self.player.pause()
            
            # Clean up old temp files
            old_temp = self.temp_file
            
            # Set new file
            self.temp_file = eq_file_path
            
            # Update spectrogram with EQ-processed audio data
            try:
                self.spectrogram.set_spectrum_data(processed_audio, sample_rate)
                # Update EQ gains in the spectrogram for visual overlay
                self.spectrogram.update_eq_gains(self._eq_bass_gain, self._eq_mid_gain, self._eq_treble_gain)
                
                print(f"Deck {self.deck_number}: Updated spectrogram with EQ-processed audio")
            except Exception as e:
                print(f"Deck {self.deck_number}: Error updating spectrogram with EQ data: {e}")
            
            # Load the new EQ-processed file
            self.player.setSource(QUrl.fromLocalFile(self.temp_file))
            
            # Clean up old file after setting new source
            # IMPORTANT: Never delete the original file, only delete actual temp files
            if (old_temp and old_temp != eq_file_path and os.path.exists(old_temp) and 
                old_temp != self.original_file_path):
                try:
                    os.remove(old_temp)
                    print(f"Deck {self.deck_number}: Cleaned up old temp file: {os.path.basename(old_temp)}")
                except Exception as e:
                    print(f"Deck {self.deck_number}: Could not remove old temp file: {e}")
            elif old_temp == self.original_file_path:
                print(f"Deck {self.deck_number}: Skipping cleanup of original file: {os.path.basename(old_temp)}")
            
            # Wait for media to load, then restore position and resume
            QTimer.singleShot(200, lambda: self._restore_eq_position_and_resume(pos_fraction, was_playing))

        except Exception as e: 
            print(f"Deck {self.deck_number}: Error in EQ processing: {e}")
            traceback.print_exc()
            
            # Show error status
            if hasattr(self, 'eq_status_label'):
                self.eq_status_label.setText("EQ Error ✗")
                QTimer.singleShot(3000, lambda: self.eq_status_label.setVisible(False))
                
            if was_playing and self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.player.play()
    
    def _restore_eq_position_and_resume(self, position_fraction, was_playing):
        """
        Restore position and resume playback after EQ processing.

        Args:
            position_fraction (float): Fractional position to restore.
            was_playing (bool): Whether playback was active before EQ.
        """
        try:
            # Check if media is loaded
            status = self.player.mediaStatus()
            if status in [QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia]:
                # Restore position
                new_duration = self.player.duration()
                if new_duration > 0:
                    target_position = int(position_fraction * new_duration)
                    target_position = max(0, min(target_position, new_duration))
                    self.player.setPosition(target_position)
                    self.update_position(target_position)
                    print(f"Deck {self.deck_number}: Restored position after EQ: {target_position}ms")
                
                # Resume playback if it was playing
                if was_playing:
                    self.player.play()
                    print(f"Deck {self.deck_number}: Resumed playback after EQ")
                
                # Show success status
                if hasattr(self, 'eq_status_label'):
                    self.eq_status_label.setText("EQ Applied ✓")
                    QTimer.singleShot(2000, lambda: self.eq_status_label.setVisible(False))
                    
            elif status in [QMediaPlayer.MediaStatus.LoadingMedia, QMediaPlayer.MediaStatus.StalledMedia, 
                           QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.NoMedia]:
                # Media still loading, try again
                print(f"Deck {self.deck_number}: Media still loading after EQ, retrying...")
                QTimer.singleShot(200, lambda: self._restore_eq_position_and_resume(position_fraction, was_playing))
            else:
                print(f"Deck {self.deck_number}: Media load failed after EQ processing (status: {status})")
                if hasattr(self, 'eq_status_label'):
                    self.eq_status_label.setText("EQ Load Error ✗")
                    QTimer.singleShot(3000, lambda: self.eq_status_label.setVisible(False))
                
        except Exception as e:
            print(f"Deck {self.deck_number}: Error restoring after EQ: {e}")
            if was_playing and self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.player.play()

    def toggle_loop(self):
        """
        Toggle the loop state for playback.
        """
        self._loop_enabled = not self._loop_enabled
        self.loop_button.setChecked(self._loop_enabled)
        
        if self._loop_enabled:
            self.loop_button.setProperty("class", "neonBorderActive")
            # Update loop times when enabling
            self._update_loop_start()
            self._update_loop_length()
        else:
            self.loop_button.setProperty("class", "neonBorder")
        
        # Update button style
        self.loop_button.style().unpolish(self.loop_button)
        self.loop_button.style().polish(self.loop_button)

    def _update_loop_start(self):
        """
        Update the loop start time from the input field.
        """
        try:
            start_time = float(self.loop_start_input.text())
            if start_time < 0:
                start_time = 0
            self._loop_start_time = int(start_time * 1000)  # Convert to milliseconds
            self._loop_end_time = self._loop_start_time + self._loop_length
            self.loop_start_input.setText(f"{start_time:.1f}")
        except ValueError:
            # Reset to current value if invalid input
            self.loop_start_input.setText(f"{self._loop_start_time / 1000:.1f}")

    def _update_loop_length(self):
        """
        Update the loop length from the input field.
        """
        try:
            length = float(self.loop_length_input.text())
            if length < 0.1:  # Minimum 100ms
                length = 0.1
            self._loop_length = int(length * 1000)  # Convert to milliseconds
            self._loop_end_time = self._loop_start_time + self._loop_length
            self.loop_length_input.setText(f"{length:.1f}")
        except ValueError:
            # Reset to current value if invalid input
            self.loop_length_input.setText(f"{self._loop_length / 1000:.1f}")