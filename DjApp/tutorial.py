import os
import json
import traceback
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QWidget, QFrame
)
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PyQt6.QtWidgets import QScrollArea

class HighlightOverlay(QWidget):
    """
    A transparent overlay widget that highlights a specific UI element.
    """
    
    def __init__(self, parent=None):
        """
        Initialize the HighlightOverlay widget.

        Args:
            parent (QWidget, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        
        self.highlight_rect = None
        self.highlight_color = QColor(243, 207, 44, 120)  # Semi-transparent yellow
        self.text = ""
        self.text_rect = None
        
    def set_highlight(self, rect, text=""):
        """
        Set the rectangle to highlight and optional text.

        Args:
            rect (QRect): Rectangle to highlight.
            text (str, optional): Text to display near the highlight. Defaults to "".
        """
        self.highlight_rect = rect
        self.text = text
        if text:
            self.text_rect = QRect(
                rect.left(),
                rect.bottom() + 10,
                rect.width(),
                50  # Fixed height for text
            )
        self.update()
        
    def paintEvent(self, event):
        """
        Custom paint event to draw the highlight.

        Args:
            event: The QPaintEvent instance.
        """
        if not self.highlight_rect:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw darkened background for everything except highlighted area
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        
        # Draw highlight area
        painter.setPen(QPen(QColor(243, 207, 44), 3))  # Yellow border
        painter.setBrush(QBrush(self.highlight_color))
        painter.drawRoundedRect(self.highlight_rect, 8, 8)
        
        # Draw text if provided
        if self.text and self.text_rect:
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            painter.drawText(self.text_rect, Qt.AlignmentFlag.AlignCenter, self.text)

class TutorialStep:
    """
    Represents a single step in the tutorial.
    """
    
    def __init__(self, title, description, target_widget=None, highlight_text=""):
        """
        Initialize a TutorialStep.

        Args:
            title (str): Title of the tutorial step.
            description (str): Description of the step.
            target_widget (QWidget, optional): Widget to highlight.
            highlight_text (str, optional): Text to show near highlight.
        """
        self.title = title
        self.description = description
        self.target_widget = target_widget  # Widget to highlight
        self.highlight_text = highlight_text  # Text to show near highlight
        
class TutorialManager(QObject):
    """
    Manages the interactive tutorial experience for new users.
    """
    
    # Signal when tutorial is complete
    tutorial_completed = pyqtSignal()
    
    def __init__(self, main_app):
        """
        Initialize the tutorial manager.

        Args:
            main_app: Reference to the main DJ application instance
        """
        super().__init__()  # Initialize QObject
        self.main_app = main_app
        self.current_step = 0
        self.tutorial_steps = []
        self.overlay = None
        self.dialog = None
        self.is_running = False
        self.config_file = self._get_config_path()
        
        # Initialize tutorial steps
        self._init_tutorial_steps()
        
    def _get_config_path(self):
        """
        Get the path to the configuration file.

        Returns:
            str: Path to the tutorial configuration file.
        """
        # Store in the same directory as the application
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, "tutorial_config.json")
        
    def _init_tutorial_steps(self):
        """
        Initialize all tutorial steps (empty until widgets are available).
        """
        # Will be populated after we have access to the widgets
        self.tutorial_steps = []
        
    def setup_tutorial_steps(self):
        """
        Set up tutorial steps with references to actual widgets.
        """
        # Clear existing steps
        self.tutorial_steps = []
        
        # Welcome step
        self.tutorial_steps.append(
            TutorialStep(
                "Welcome to MixLab DJ!",
                "This tutorial will guide you through the basics of DJing with our app. "
                "We'll cover loading tracks, controlling playback, adjusting volume, "
                "and using basic DJ techniques like beatmatching and crossfading.\n\n"
                "Click 'Next' to continue or 'Skip Tutorial' to exit.",
                None
            )
        )
        
        # Step 1: Loading tracks
        self.tutorial_steps.append(
            TutorialStep(
                "Loading Tracks",
                "First, you'll need to load some music. Click the 'Select Audio Directory' "
                "button to choose a folder with your music files.",
                self.main_app.findChild(QPushButton, "select_dir_button"),
                "Click here to select your music folder"
            )
        )
        
        # Step 2: Track browser
        self.tutorial_steps.append(
            TutorialStep(
                "Track Browser",
                "After selecting a directory, click 'Show Track List' to browse your music. "
                "From there, you can load tracks into Deck 1 or Deck 2.",
                self.main_app.track_list_button,
                "Click here to browse your tracks"
            )
        )
        
        # Step 3: Deck controls
        self.tutorial_steps.append(
            TutorialStep(
                "Deck Controls",
                "Each deck has play/pause and other controls to manage playback. "
                "The waveform display shows you a visual representation of the audio. "
                "The colored markers indicate beats to help with mixing.",
                self.main_app.deck1,
                "Deck 1 controls"
            )
        )
        
        # Step 4: Volume controls
        self.tutorial_steps.append(
            TutorialStep(
                "Volume Controls",
                "Each deck has its own volume slider. The Master Volume controls "
                "the overall output level of your mix.",
                self.main_app.master_volume_slider,
                "Master Volume"
            )
        )
        
        # Step 5: Crossfader
        self.tutorial_steps.append(
            TutorialStep(
                "Crossfader",
                "The crossfader lets you transition between decks. Move it left for Deck 1, "
                "right for Deck 2, or center to hear both decks equally.\n\n"
                "This is one of the most important tools for smooth transitions!",
                self.main_app.crossfader,
                "Crossfader: Slide to mix between decks"
            )
        )
        
        # Step 6: BPM and Tempo
        self.tutorial_steps.append(
            TutorialStep(
                "BPM and Tempo Control",
                "BPM (Beats Per Minute) is the speed of your track. Use the +/- buttons "
                "to adjust the tempo. Matching BPMs between tracks is called 'beatmatching' "
                "and is essential for smooth mixing.",
                self.main_app.deck1.bpm_display if hasattr(self.main_app.deck1, "bpm_display") else None,
                "BPM Controls"
            )
        )
        
        # Step 7: Loop Controls
        self.tutorial_steps.append(
            TutorialStep(
                "Loop Controls",
                "The loop feature lets you repeat a section of your track continuously. "
                "Simply enter the number of seconds you want to loop and the starting point, and the track will "
                "repeat that section until you disable the loop.\n\n"
                "This is great for:\n"
                "• Extending intros or outros\n"
                "• Creating build-ups\n"
                "• Practicing transitions\n"
                "• Adding creative effects to your mix",
                self.main_app.deck1.loop_button if hasattr(self.main_app.deck1, "loop_button") else None,
                "Loop Controls: Set start time and length, then click to activate"
            )
        )
        
        # Step 8: Sync
        self.tutorial_steps.append(
            TutorialStep(
                "Sync Function",
                "The SYNC button automatically matches the tempo and beat alignment "
                "between decks. It's perfect for beginners learning to mix!\n\n"
                "First click SYNC on one deck to make it the master, then click SYNC "
                "on the other deck to match its tempo and beats.",
                self.main_app.deck1.sync_button if hasattr(self.main_app.deck1, "sync_button") else None,
                "Sync button"
            )
        )
        
        # Step 9: Recording
        self.tutorial_steps.append(
            TutorialStep(
                "Recording Your Mix",
                "When you're ready to save your mix, use the Record button. "
                "First set a recording folder, then click Record to start/stop recording.",
                self.main_app.record_button,
                "Record button"
            )
        )
        
        # Final step
        self.tutorial_steps.append(
            TutorialStep(
                "You're Ready to Mix!",
                "That's it for the basics! Remember, you can access the Help button "
                "anytime to review these concepts. Now go ahead and create some amazing mixes!\n\n"
                "Click 'Finish' to start using MixLab DJ.",
                None
            )
        )
        
    def is_first_launch(self):
        """
        Check if this is the first time the app has been launched.

        Returns:
            bool: True if first launch, False otherwise.
        """
        if not os.path.exists(self.config_file):
            print("Tutorial config file not found, assuming first launch")
            return True
            
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                
                # Check if tutorial is enabled
                tutorial_enabled = config.get('tutorial_enabled', True)
                if not tutorial_enabled:
                    print("Tutorial is disabled in settings")
                    return False
                
                is_first = not config.get('tutorial_completed', False)
                print(f"Tutorial completed status: {not is_first}")
                return is_first
        except Exception as e:
            print(f"Error reading tutorial config: {e}")
            # If there's any error reading the file, assume first launch
            return True
            
    def mark_tutorial_completed(self):
        """
        Mark the tutorial as completed in the configuration.
        """
        try:
            # Load existing config or create new one
            config = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
            
            # Update tutorial completion status
            config['tutorial_completed'] = True
            
            # Preserve tutorial_enabled setting if it exists
            if 'tutorial_enabled' not in config:
                config['tutorial_enabled'] = True
            
            # Save updated config
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
                
        except Exception as e:
            print(f"Error saving tutorial configuration: {e}")
                
    def start_tutorial(self):
        """
        Start the interactive tutorial.
        """
        print("Tutorial start requested")
        if self.is_running:
            print("Tutorial already running, ignoring start request")
            return
            
        print("Initializing tutorial...")
        self.is_running = True
        self.current_step = 0
        
        # Set up steps with actual widget references
        print("Setting up tutorial steps...")
        self.setup_tutorial_steps()
        
        # Create overlay for highlighting
        print("Creating tutorial overlay...")
        self.overlay = HighlightOverlay(self.main_app)
        self.overlay.setGeometry(self.main_app.geometry())
        
        try:
            print("Showing overlay...")
            self.overlay.show()
            
            # Show the first step
            print("Showing first tutorial step...")
            self._show_current_step()
            print("Tutorial started successfully")
        except Exception as e:
            print(f"Error during tutorial start: {e}")
            traceback.print_exc()
            self.stop_tutorial()
        
    def stop_tutorial(self):
        """
        Stop the tutorial and clean up overlay/dialog.
        """
        self.is_running = False
        
        if self.dialog:
            self.dialog.close()
            self.dialog = None
            
        if self.overlay:
            self.overlay.close()
            self.overlay = None
            
        # Mark tutorial as completed
        self.mark_tutorial_completed()
        self.tutorial_completed.emit()
        
    def _show_current_step(self):
        """
        Show the current tutorial step, update overlay and dialog.
        """
        if not self.is_running or self.current_step >= len(self.tutorial_steps):
            self.stop_tutorial()
            return
            
        step = self.tutorial_steps[self.current_step]
        
        # Update highlight overlay
        if self.overlay:
            if step.target_widget:
                # Map the widget's geometry to global coordinates
                global_rect = step.target_widget.geometry()
                if hasattr(step.target_widget, 'mapToGlobal'):
                    global_pos = step.target_widget.mapToGlobal(QPoint(0, 0))
                    global_rect.moveTopLeft(global_pos)
                    # Map back to overlay coordinates
                    overlay_pos = self.overlay.mapFromGlobal(global_pos)
                    global_rect.moveTopLeft(overlay_pos)
                
                self.overlay.set_highlight(global_rect, step.highlight_text)
            else:
                self.overlay.set_highlight(None)
            
        # Create or update the dialog
        if not self.dialog:
            self.dialog = QDialog(self.main_app)
            self.dialog.setWindowTitle("MixLab DJ Tutorial")
            self.dialog.setObjectName("tutorialDialog")
            self.dialog.setWindowFlags(
                Qt.WindowType.Dialog | 
                Qt.WindowType.FramelessWindowHint | 
                Qt.WindowType.WindowStaysOnTopHint
            )

            
            # Create layout
            layout = QVBoxLayout(self.dialog)
            
            # Title
            self.title_label = QLabel()
            self.title_label.setObjectName("tutorialTitle")
            layout.addWidget(self.title_label)
            
            # Description
            self.desc_label = QLabel()
            self.desc_label.setObjectName("tutorialDescription")
            self.desc_label.setWordWrap(True)
            layout.addWidget(self.desc_label)
            
            # Buttons
            buttons_layout = QHBoxLayout()
            
            self.prev_button = QPushButton("Previous")
            self.prev_button.clicked.connect(self._go_to_previous_step)
            
            self.next_button = QPushButton("Next")
            self.next_button.setObjectName("nextButton")
            self.next_button.clicked.connect(self._go_to_next_step)
            
            self.skip_button = QPushButton("Skip Tutorial")
            self.skip_button.clicked.connect(self.stop_tutorial)
            
            buttons_layout.addWidget(self.prev_button)
            buttons_layout.addWidget(self.skip_button)
            buttons_layout.addWidget(self.next_button)
            
            layout.addLayout(buttons_layout)
            
            # Set fixed size
            self.dialog.setMinimumWidth(400)
            self.dialog.setMaximumWidth(500)
            
            # Position at bottom right
            self._position_dialog()
            
            self.dialog.show()
        
        # Update dialog content
        self.title_label.setText(step.title)
        self.desc_label.setText(step.description)
        
        # Update buttons
        self.prev_button.setEnabled(self.current_step > 0)
        
        # Change Next to Finish on last step
        if self.current_step == len(self.tutorial_steps) - 1:
            self.next_button.setText("Finish")
        else:
            self.next_button.setText("Next")
    
    def _position_dialog(self):
        """
        Position the tutorial dialog in an appropriate place.
        """
        if not self.dialog or not self.main_app:
            return
            
        # Position at bottom right of main window
        main_geo = self.main_app.geometry()
        dialog_width = self.dialog.width()
        dialog_height = self.dialog.height()
        
        # If dialog size is not yet determined, set default
        if dialog_width < 100 or dialog_height < 100:
            dialog_width = 400
            dialog_height = 300
            
        # Position at bottom right with some padding
        x = main_geo.x() + main_geo.width() - dialog_width - 20
        y = main_geo.y() + main_geo.height() - dialog_height - 20
        
        # Ensure dialog is visible on screen
        if x < 0:
            x = 0
        if y < 0:
            y = 0
            
        self.dialog.setGeometry(x, y, dialog_width, dialog_height)
        
    def _go_to_next_step(self):
        """
        Advance to the next tutorial step.
        """
        self.current_step += 1
        
        # If we've reached the end, stop the tutorial
        if self.current_step >= len(self.tutorial_steps):
            self.stop_tutorial()
        else:
            self._show_current_step()
            
    def _go_to_previous_step(self):
        """
        Go back to the previous tutorial step.
        """
        if self.current_step > 0:
            self.current_step -= 1
            self._show_current_step()
            
    def update_overlay_position(self):
        """
        Update the position of the overlay if main window moves/resizes.
        """
        if self.overlay and self.is_running:
            self.overlay.setGeometry(self.main_app.geometry())
            self._show_current_step()  # Refresh the current step
            self._position_dialog()
            
class ConceptsGuide(QDialog):
    """
    A guide explaining core DJ concepts in plain language.
    """
    
    def __init__(self, parent=None):
        """
        Initialize the ConceptsGuide dialog.

        Args:
            parent (QWidget, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setObjectName("conceptsGuide")
        self.setWindowTitle("DJ Concepts Guide")
        self.setMinimumSize(600, 500)
        self.setup_ui()
        
    def setup_ui(self):
        """
        Set up the user interface for the concepts guide dialog.
        """
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Core DJ Concepts - Explained Simply")
        title.setObjectName("conceptsTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Create scrollable content area
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        # Add concepts
        concepts = [
            ("Beatmatching", 
             "Beatmatching is when you make two songs play at the same speed (BPM) so their beats align perfectly. "
             "It's like making sure two car engines are running at exactly the same speed before merging them together.\n\n"
             "How to do it:\n"
             "• Use the BPM display to see each track's speed\n"
             "• Use the +/- buttons to adjust tempo until BPMs match\n"
             "• Use SYNC for automatic beatmatching (great for beginners!)\n"
             "• Watch the waveforms to visually align the beats"),
             
            ("Crossfading",
             "Crossfading is smoothly transitioning from one track to another. Think of it like a see-saw: "
             "as one side goes up (gets louder), the other goes down (gets quieter).\n\n"
             "How to do it:\n"
             "• Start with crossfader in position for current track\n"
             "• Gradually move it toward the other track\n"
             "• Move slowly for smooth transitions, quickly for cuts\n"
             "• Best done when beats are matched!"),
             
            ("Phrases & Structure",
             "Most dance music is structured in phrases of 8, 16, or 32 beats. Mixing works best when "
             "you align these phrases - like making sure sentences start and end at natural points.\n\n"
             "How to use phrases:\n"
             "• Count beats in groups of 8 (1,2,3,4,5,6,7,8...)\n"
             "• Start transitions at the beginning of phrases\n" 
             "• Complete transitions by the start of new phrases\n"
             "• The waveform display helps identify phrases visually"),
             
            ("EQ Mixing",
             "EQ mixing means adjusting bass, mid, and treble frequencies when mixing. "
             "It's like making room in a crowded elevator - you reduce elements in one track "
             "to make space for similar elements in the other.\n\n"
             "Basic technique:\n"
             "• Reduce bass on incoming track before crossfading\n"
             "• Gradually restore bass as crossfade completes\n"
             "• Avoid frequency clashing by adjusting EQs on both tracks"),
             
             
            ("Looping",
             "Looping is repeating a specific section of a track continuously. It's like putting "
             "a small part of the song on repeat to extend a moment or create tension.\n\n"
             "Common uses for loops:\n"
             "• Extend intros/outros for longer mixing transitions\n"
             "• Create build-ups by looping a rising section\n"
             "• Keep a vocal or instrumental section going\n"
             "• Fix timing issues by extending sections\n"
             "• Create custom edits during live performance\n\n"
             "Pro tip: Try looping 4, 8, or 16-beat sections to maintain the musical phrase structure."),
             
            ("Auto Mix",
             "Auto Mix is like having an automatic DJ assistant that perfectly syncs two tracks for you."
             "It makes sure both songs play at the same speed and that their beats hit at the exact same time—so transitions sound clean and professional, without you lifting a finger.\n\n"
             "How it works (with one click):\n"
             "• Checks that both decks have songs loaded\n"
             "• Verifies both tracks have BPM and beat positions analyzed\n"
             "• Calculates a shared tempo between the two songs\n"
             "• Adjusts both songs to that tempo\n"
             "• Aligns the beats so kicks and snares hit together\n"
             "• Ready for a smooth crossfade—no awkward timing!\n\n"
             "Pro tip: Use Auto Mix before crossfading to make transitions sound like a live DJ set.")
        ]
        
        for title, description in concepts:
            # Create frame for each concept
            frame = QFrame()
            frame.setObjectName("conceptFrame")
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            
            concept_layout = QVBoxLayout(frame)
            
            # Concept title
            concept_title = QLabel(title)
            concept_title.setObjectName("conceptTitle")
            concept_layout.addWidget(concept_title)
            
            # Description
            concept_desc = QLabel(description)
            concept_desc.setObjectName("conceptDescription")
            concept_desc.setWordWrap(True)
            concept_layout.addWidget(concept_desc)
            
            scroll_layout.addWidget(frame)
        
        # Add a note at the end
        note = QLabel("Remember: Practice makes perfect! Even professional DJs started as beginners.")
        note.setObjectName("conceptsNote")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_layout.addWidget(note)
        
        # Add some stretch at the end
        scroll_layout.addStretch()
        
        # Create scroll area and add content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.setObjectName("conceptsCloseButton")
        close_button.clicked.connect(self.accept)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        button_layout.addStretch()
        layout.addLayout(button_layout) 