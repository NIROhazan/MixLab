import os
# PyQt6 Imports
from PyQt6.QtWidgets import (QDialog, QListWidget, QListWidgetItem, QLabel, 
                           QVBoxLayout, QHBoxLayout, QPushButton, QWidget, 
                           QSizePolicy, QMessageBox)
from PyQt6.QtCore import QSize, pyqtSignal, QThread


class BPMAnalyzerThread(QThread):
    """
    Thread for analyzing BPM of audio files in the background.
    Emits signals when BPM is analyzed for a file and when analysis is completed.
    """
    # Signal to update UI when BPM is analyzed
    bpm_analyzed = pyqtSignal(str, float)
    analysis_completed = pyqtSignal()

    def __init__(self, audio_analyzer, directory, file_list):
        """
        Initialize the AudioAnalyzerThread.

        Args:
            audio_analyzer: Instance of AudioAnalyzerBridge or compatible analyzer.
            directory (str): Directory containing audio files.
            file_list (list): List of audio file names to analyze.
        """
        super().__init__()
        self.audio_analyzer = audio_analyzer
        self.directory = directory
        self.file_list = file_list
        self.running = True

    def run(self):
        """
        Run the BPM analysis for each file in the list.
        Emits bpm_analyzed for each file and analysis_completed when done.
        """
        for file in self.file_list:
            if not self.running:
                break

            try:
                if self.audio_analyzer:
                    file_path = os.path.join(self.directory, file)
                    # Get BPM from regular analysis (30 seconds is sufficient for BPM)
                    bpm, _ = self.audio_analyzer.analyze_file(file_path)
                    
                    if bpm > 0:
                        # Pre-cache full track beat positions for later use
                        try:
                            full_track_beats = self.audio_analyzer.get_full_track_beat_positions_ms(file_path)
                            # The get_full_track_beat_positions_ms method will automatically cache the results
                            print(f"Pre-cached full track beats for {file}: {len(full_track_beats)} beats")
                        except Exception as beat_error:
                            print(f"Full track beat analysis failed for {file}: {beat_error}")
                            
                        # Emit signal with analyzed BPM
                        self.bpm_analyzed.emit(file, bpm)
                    
            except Exception as e:
                print(f"Thread BPM analysis error for {file}: {str(e)}")

        # Signal that all files have been analyzed
        self.analysis_completed.emit()

    def stop(self):
        """
        Stop the BPM analysis thread.
        """
        self.running = False
    
    def add_files(self, new_files):
        """
        Add new files to the analysis queue.
        
        Args:
            new_files (list): List of new file names to analyze.
        """
        # Extend the file list with new files
        self.file_list.extend(new_files)

class FileBrowserDialog(QDialog):
    """
    Dialog for browsing and selecting audio files, with BPM analysis and deck loading support.
    """
    # Define signal to emit when a file is selected for loading
    file_selected = pyqtSignal(int, str)
    bpm_analyzed = pyqtSignal(str, float)  # Add signal for BPM analysis

    def __init__(self, directory, parent=None, audio_analyzer=None, cache_manager=None):
        """
        Initialize the FileBrowserDialog.

        Args:
            directory (str): Directory to display.
            parent (QWidget, optional): Parent widget.
            audio_analyzer: Instance of AudioAnalyzerBridge or compatible analyzer.
            cache_manager: Instance of AudioCacheManager for persistent caching.
        """
        super().__init__(parent)
        self.directory = directory
        self.audio_analyzer = audio_analyzer
        self.cache_manager = cache_manager  # Use provided cache manager
        self.track_items = {}
        self.bpm_cache = {}
        self.status_label = QLabel("Select an audio directory first.")
        self.analyzer_thread = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(600, 400) # Adjusted minimum size
        self.initUI()
        
        # Set proper window title and populate list if directory is provided
        if self.directory and os.path.isdir(self.directory):
            self.setWindowTitle(f"Track List - {os.path.basename(directory)}")
            self.populate_file_list()
        else:
            self.setWindowTitle("Track List")

    def resizeEvent(self, event):
        """
        Handle dialog resize events to adjust item sizes.

        Args:
            event: The QResizeEvent instance.
        """
        super().resizeEvent(event)
        if hasattr(self, 'list_widget'):
            width = self.width()
            item_height = 150
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item:
                    item.setSizeHint(QSize(width - 40, item_height))

    def initUI(self):
        """
        Initialize the user interface for the file browser dialog.
        """
        # Set class for external stylesheet
        self.setProperty("class", "fileBrowserDialog")
        self.setStyle(self.style())  # Force style update
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Add status label at the top
        self.status_label.setProperty("class", "fileBrowserStatus")
        self.status_label.setStyle(self.status_label.style())  # Force style update
        layout.addWidget(self.status_label)

        self.list_widget = QListWidget()
        self.list_widget.setProperty("class", "fileBrowserList")
        self.list_widget.setStyle(self.list_widget.style())  # Force style update
        layout.addWidget(self.list_widget)
        # self.setLayout(layout) # Set layout automatically via self

    def set_directory(self, directory):
        """
        Set the directory and repopulate the list.

        Args:
            directory (str): Directory to display.
        """
        self.directory = directory
        if self.directory and os.path.isdir(self.directory):
             self.setWindowTitle(f"Track List - {os.path.basename(directory)}")
             self.populate_file_list()
        else:
             self.setWindowTitle("Track List")
             self.list_widget.clear()
             self.status_label.setText("Invalid directory selected.")
             self.directory = None

    def closeEvent(self, event):
        """
        Handle dialog close event to stop any running thread.

        Args:
            event: The QCloseEvent instance.
        """
        if self.analyzer_thread and self.analyzer_thread.isRunning():
            self.analyzer_thread.stop()
            self.analyzer_thread.wait()
        super().closeEvent(event) # Call base class method

    def populate_file_list(self):
        """
        Populates the list with audio files in the selected folder.
        """
        self.list_widget.clear()
        self.track_items = {}

        if not self.directory or not os.path.isdir(self.directory):
            self.status_label.setText("No valid directory selected.")
            return

        # Get all audio files (add more formats if needed)
        audio_files = []
        try:
            for file in os.listdir(self.directory):
                if file.lower().endswith((".mp3", ".wav", ".flac")):
                    audio_files.append(file)
        except OSError as e:
            self.status_label.setText(f"Error accessing directory: {e}")
            return

        if not audio_files:
            self.status_label.setText("No compatible audio tracks found.")
            QMessageBox.information(self, "No Audio Files", "No compatible audio tracks found in the selected directory.")
            return

        # First check cache and create UI elements for all files
        files_to_analyze = []
        cached_from_persistent = 0
        cached_from_memory = 0
        
        for file in audio_files:
            full_path = os.path.join(self.directory, file)
            cached_bpm = 0
            
            # Check persistent cache first
            if self.cache_manager:
                cached_data = self.cache_manager.get_bpm_data(full_path)
                if cached_data and cached_data[0] is not None:
                    cached_bpm = cached_data[0]
                    # Update in-memory cache
                    self.bpm_cache[full_path] = cached_bpm
                    cached_from_persistent += 1
            
            # If not in persistent cache, check in-memory cache
            if cached_bpm == 0:
                cached_bpm = self.bpm_cache.get(full_path, 0)
                if cached_bpm > 0:
                    cached_from_memory += 1
            
            # Add track to list with BPM if we have it
            if cached_bpm > 0:
                self.add_track_to_list(file, cached_bpm)
            else:
                files_to_analyze.append(file)
                self.add_track_to_list(file, 0)  # Add to UI without BPM

        cached_count = cached_from_persistent + cached_from_memory
        
        # Update status message based on cache and analysis state
        if cached_count > 0:
            if files_to_analyze:
                self.status_label.setText(f"{cached_count} tracks ready, analyzing {len(files_to_analyze)} more...")
            else:
                self.status_label.setText(f"All {cached_count} tracks ready!")
        else:
            self.status_label.setText(f"Analyzing {len(files_to_analyze)} tracks...")

        # Only start analysis thread if there are files that need analysis
        if files_to_analyze and self.audio_analyzer:
            # Create new analyzer thread only if one doesn't exist or isn't running
            if not self.analyzer_thread or not self.analyzer_thread.isRunning():
                self.analyzer_thread = BPMAnalyzerThread(self.audio_analyzer, self.directory, files_to_analyze)
                self.analyzer_thread.bpm_analyzed.connect(self.update_track_bpm)
                self.analyzer_thread.analysis_completed.connect(self.analysis_completed)
                self.analyzer_thread.start()
            else:
                # If thread is already running, add new files to its queue
                self.analyzer_thread.add_files(files_to_analyze)
        else:
            # If all files were cached, mark as complete
            self.analysis_completed()              

    def add_track_to_list(self, file, bpm=0):
        """
        Add a track to the list widget with yellow theme.

        Args:
            file (str): File name of the audio track.
            bpm (float, optional): BPM value if already known.
        """
        item = QListWidgetItem(self.list_widget)
        # Increase height to accommodate buttons with spacing
        item.setSizeHint(QSize(self.list_widget.width() - 40, 150))
        
        widget = QWidget()
        item_layout = QHBoxLayout(widget)
        item_layout.setContentsMargins(10, 10, 10, 20)  # Increased bottom margin
        item_layout.setSpacing(15)

        # Left side layout for file name
        left_layout = QVBoxLayout()
        left_layout.setSpacing(5)
        left_layout.setContentsMargins(0, 0, 0, 10)  # Added bottom margin
        
        # Create display name with BPM if available
        base_name = os.path.splitext(os.path.basename(file))[0]
        display_name = base_name
        if bpm > 0:
            display_name = f"{base_name} ({int(bpm)} BPM)"
        
        file_label = QLabel(display_name)
        file_label.setProperty("class", "fileBrowserFileName")
        file_label.setStyle(file_label.style())  # Force style update
        file_label.setWordWrap(True)
        file_label.setToolTip(display_name)
        left_layout.addWidget(file_label)
        left_layout.addStretch()

        # Right side layout for buttons with fixed width
        buttons_layout = QHBoxLayout()  # Changed to QHBoxLayout for side by side buttons
        buttons_layout.setSpacing(15)  # Horizontal spacing between buttons
        buttons_layout.setContentsMargins(0, 5, 0, 15)
        
        button1 = QPushButton("Load Deck 1")
        button2 = QPushButton("Load Deck 2")
        button1.setFixedWidth(100)
        button2.setFixedWidth(100)
        
        # Set classes for external stylesheet
        button1.setProperty("class", "fileBrowserLoadButton")
        button2.setProperty("class", "fileBrowserLoadButton")
        button1.setStyle(button1.style())  # Force style update
        button2.setStyle(button2.style())  # Force style update
        
        buttons_layout.addWidget(button1)
        buttons_layout.addWidget(button2)

        # Connect buttons to emit the signal
        full_path = os.path.join(self.directory, file)
        button1.clicked.connect(lambda checked=False, p=full_path: self.file_selected.emit(1, p))
        button2.clicked.connect(lambda checked=False, p=full_path: self.file_selected.emit(2, p))

        # Wrap the horizontal button layout in a vertical layout to maintain alignment
        right_container = QVBoxLayout()
        right_container.addLayout(buttons_layout)
        right_container.addStretch()  # Push buttons to the top

        # Add layouts to main item layout
        item_layout.addLayout(left_layout, stretch=1)  # Give file name area more space
        item_layout.addLayout(right_container)  # Buttons take minimum needed space

        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, widget)

        # Store item for later BPM update
        self.track_items[file] = (item, file_label)

    def update_track_bpm(self, file, bpm):
        """
        Update the BPM display for a track after background analysis.

        Args:
            file (str): File name of the audio track.
            bpm (float): BPM value.
        """
        if file in self.track_items and bpm > 0:
            # Cache the BPM result
            full_path = os.path.join(self.directory, file)
            self.bpm_cache[full_path] = bpm
            
            item, label = self.track_items[file]

            # Update display name with BPM
            display_name = f"{os.path.splitext(file)[0]} ({int(bpm)} BPM)"
            label.setText(display_name)
            label.setToolTip(display_name)

            # Update status to show progress
            analyzed_count = sum(1 for _, lbl in self.track_items.values()
                               if "BPM" in lbl.text())
            total_count = len(self.track_items)
            remaining = total_count - analyzed_count
            
            if remaining > 0:
                self.status_label.setText(f"Analyzing BPM: {analyzed_count} done, {remaining} remaining...")
            else:
                self.status_label.setText(f"All {total_count} tracks analyzed!")
            
            # Emit signal for the main app to update its cache
            self.bpm_analyzed.emit(full_path, bpm)

    def analysis_completed(self):
        """
        Called when all tracks have been analyzed.
        """
        # Simple completion message - detailed status already handled in update_track_bpm
        self.status_label.setText("Analysis complete!")

    def get_cached_bpm(self, file_path):
        """
        Get cached BPM for a file if available.

        Args:
            file_path (str): Path to the audio file.
        Returns:
            float: Cached BPM value or 0 if not available.
        """
        return self.bpm_cache.get(file_path, 0)

 