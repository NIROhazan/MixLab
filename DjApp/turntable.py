import math
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QPalette, QRadialGradient, QLinearGradient, QFont 
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPointF, QRectF 


class Turntable(QWidget):
    """
    Custom QWidget representing a DJ turntable with interactive rotation, pitch, and scratching.
    Emits signals for position scrubbing and pitch changes.
    """
    # Signal emitted when the user scrubs (drags) the turntable
    # Passes the new position as a fraction (0.0 to 1.0)
    positionScrubbed = pyqtSignal(float)
    # Signal for pitch/speed control from outer ring
    pitchChanged = pyqtSignal(float)  # -8 to +8 range for typical DJ pitch

    def __init__(self, parent=None):
        """
        Initialize the Turntable widget.

        Args:
            parent (QWidget, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.angle = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.timer.setInterval(20)  # 50 FPS

        # Add debounce timer for seeking
        self.seek_timer = QTimer(self)
        self.seek_timer.setSingleShot(True)
        self.seek_timer.timeout.connect(self._emit_seek_position)
        self.pending_seek_position = None

        self.is_dragging = False
        self.is_outer_ring = False  # Track if user is dragging outer ring
        self._is_playing = False
        self._was_playing = False
        self.last_mouse_pos = QPointF()
        self.base_rotation_speed = 2.5
        self.rotation_speed = self.base_rotation_speed
        self.current_pitch = 0.0  # Current pitch adjustment (-8 to +8)
        self.last_y = None  # For vertical pitch control

        # Animation properties
        self._hover_opacity = 0.0
        self._glow_phase = 0.0
        self._glow_timer = QTimer(self)
        self._glow_timer.timeout.connect(self._update_glow)
        self._glow_timer.start(50)  # 20 FPS

        # Styling
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(150, 150)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.transparent)
        self.setPalette(palette)

        # Enhanced color definitions
        self.colors = {
            'base': QColor(17, 17, 17, 200),
            'primary': QColor("#f3cf2c"),
            'glow': QColor("#f3cf2c"),
            'outer_ring': QColor("#f3cf2c").darker(120)
        }

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)

    def _update_glow(self):
        """
        Update the glow phase for animation and trigger repaint if needed.
        """
        self._glow_phase = (self._glow_phase + 0.15) % (2 * math.pi)  # Faster animation
        # Always update to show continuous glow animation
        self.update()

    def enterEvent(self, event):
        """
        Handle mouse enter event to update hover opacity.

        Args:
            event: The QEnterEvent instance.
        """
        self._hover_opacity = 0.3
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """
        Handle mouse leave event to reset hover opacity.

        Args:
            event: The QLeaveEvent instance.
        """
        self._hover_opacity = 0.0
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        """
        Paint the turntable, including rings, grooves, hub, and indicators.

        Args:
            event: The QPaintEvent instance.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        center = QPointF(width / 2.0, height / 2.0)
        radius = min(width, height) / 2.0 - 10.0

        if radius <= 0:
            return

        # Draw outer ring (pitch control area)
        outer_ring_width = radius * 0.2
        outer_radius = radius
        inner_radius = radius - outer_ring_width
        
        # Draw outer ring with gradient
        outer_gradient = QRadialGradient(center, outer_radius)
        outer_gradient.setColorAt(0.8, self.colors['outer_ring'])  # Start of outer ring
        outer_gradient.setColorAt(1, self.colors['primary'])  # Edge of outer ring
        
        painter.setBrush(QBrush(outer_gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, outer_radius, outer_radius)
        
        # Draw inner circle (scratch area)
        base_gradient = QRadialGradient(center, inner_radius)
        base_gradient.setColorAt(0, self.colors['base'])
        base_gradient.setColorAt(0.7, QColor(30, 30, 30, 200))
        base_gradient.setColorAt(1, QColor(40, 40, 40, 200))
        
        painter.setBrush(QBrush(base_gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, inner_radius, inner_radius)

        # Draw concentric rings with enhanced glow effect
        num_rings = 3
        ring_spacing = inner_radius / (num_rings + 1)
        for i in range(num_rings):
            ring_radius = ring_spacing * (i + 1)
            glow_intensity = abs(math.sin(self._glow_phase + i * math.pi / num_rings))
            ring_color = QColor(self.colors['primary'])
            # Enhanced alpha range for more visible animation
            ring_color.setAlpha(int(80 + glow_intensity * 120))
            
            pen = QPen(ring_color, 2)  # Thicker lines
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, ring_radius, ring_radius)

        # Draw grooves
        num_grooves = 20
        groove_spacing = inner_radius / num_grooves
        for i in range(num_grooves):
            groove_radius = groove_spacing * (i + 1)
            groove_color = QColor(self.colors['primary'])
            groove_color.setAlpha(20)
            pen = QPen(groove_color, 0.5)
            painter.setPen(pen)
            painter.drawEllipse(center, groove_radius, groove_radius)

        # Draw center hub with metallic effect
        hub_radius = radius * 0.15
        hub_gradient = QRadialGradient(center, hub_radius)
        hub_gradient.setColorAt(0, QColor("#ffffff"))
        hub_gradient.setColorAt(0.5, self.colors['primary'])
        hub_gradient.setColorAt(1, QColor("#a08a1f"))
        
        painter.setBrush(QBrush(hub_gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, hub_radius, hub_radius)

        # Draw position indicator with glow
        painter.save()
        painter.translate(center)
        painter.rotate(self.angle)

        # Draw glowing line with enhanced animation
        line_gradient = QLinearGradient(0, -hub_radius, 0, -radius)
        glow_intensity = abs(math.sin(self._glow_phase))
        primary_color = self.colors['primary']
        glow_color = QColor(primary_color)
        # Enhanced alpha range for more visible pulsing
        glow_color.setAlpha(int(180 + glow_intensity * 75))
        
        line_gradient.setColorAt(0, glow_color)
        line_gradient.setColorAt(1, QColor(primary_color.red(), 
                                         primary_color.green(),
                                         primary_color.blue(), 
                                         120))
        
        # Draw main line with enhanced thickness
        painter.setPen(QPen(QBrush(line_gradient), 3))
        painter.drawLine(QPointF(0, -hub_radius), QPointF(0, -radius))

        # Add enhanced glow effect (always visible)
        glow_pen = QPen(self.colors['glow'], 6)
        glow_pen.setColor(QColor(primary_color.red(),
                               primary_color.green(),
                               primary_color.blue(),
                               int(60 + glow_intensity * 80)))
        painter.setPen(glow_pen)
        painter.drawLine(QPointF(0, -hub_radius), QPointF(0, -radius))

        painter.restore()

        # Draw pitch indicator if pitch is not 0
        if self.current_pitch != 0:
            pitch_text = f"{self.current_pitch:+.1f}%"
            painter.setPen(QPen(self.colors['primary']))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(QRectF(0, height - 20, width, 20), 
                           Qt.AlignmentFlag.AlignCenter, pitch_text)

        # Add hover effect
        if self._hover_opacity > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            hover_color = QColor(self.colors['primary'])
            hover_color.setAlpha(int(self._hover_opacity * 50))
            painter.setBrush(QBrush(hover_color))
            painter.drawEllipse(center, radius, radius)

    def set_playing(self, playing):
        """
        Controls visual rotation based on player state.

        Args:
            playing (bool): Whether the turntable should be rotating (playing state).
        """
        self._is_playing = playing
        if playing and not self.timer.isActive() and not self.is_dragging:
            self.timer.start()
        elif not playing and self.timer.isActive():
            self.timer.stop()

    def mousePressEvent(self, event):
        """
        Handle mouse press events for scratching or pitch control.

        Args:
            event: The QMouseEvent instance.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            center = QPointF(self.width() / 2, self.height() / 2)
            radius = min(self.width(), self.height()) / 2.0 - 10.0
            dist_from_center = QPointF(event.position() - center).manhattanLength()
            
            # Check if click is in outer ring (last 20% of radius)
            outer_ring_start = radius * 0.8
            self.is_outer_ring = dist_from_center >= outer_ring_start
            
            self.is_dragging = True
            self._was_playing = self._is_playing
            
            # For outer ring pitch control
            if self.is_outer_ring:
                self.last_y = event.position().y()
            else:
                # Inner area for scratching
                if self.timer.isActive():
                    self.timer.stop()
                self.last_mouse_pos = event.position()
            
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """
        Handle mouse move events for interactive rotation or pitch adjustment.

        Args:
            event: The QMouseEvent instance.
        """
        if self.is_dragging:
            if self.is_outer_ring:
                # Outer ring: Vertical movement controls pitch
                if self.last_y is not None:
                    y_diff = event.position().y() - self.last_y
                    # Convert vertical movement to pitch change
                    # Scale factor determines sensitivity
                    pitch_change = -y_diff * 0.1  # Negative because up should increase pitch
                    new_pitch = max(-8.0, min(8.0, self.current_pitch + pitch_change))
                    if new_pitch != self.current_pitch:
                        self.current_pitch = new_pitch
                        # Update rotation speed based on pitch
                        self.rotation_speed = self.base_rotation_speed * (1.0 + (self.current_pitch / 100.0))
                        self.pitchChanged.emit(self.current_pitch)
                    self.last_y = event.position().y()
            else:
                # Inner area: Traditional scratching
                current_pos = event.position()
                center = QPointF(self.width() / 2, self.height() / 2)
                
                prev_angle = math.atan2(self.last_mouse_pos.y() - center.y(), 
                                      self.last_mouse_pos.x() - center.x())
                current_angle = math.atan2(current_pos.y() - center.y(),
                                         current_pos.x() - center.x())
                
                angle_change = math.degrees(current_angle - prev_angle)
                if angle_change > 180:
                    angle_change -= 360
                elif angle_change < -180:
                    angle_change += 360
                    
                self.last_mouse_pos = current_pos
                
                new_angle = (self.angle + angle_change) % 360.0
                self.angle = new_angle

                # Emit seek position more frequently for responsive scratching
                self.pending_seek_position = self.angle / 360.0
                if not self.seek_timer.isActive():
                    self.seek_timer.start(16)  # ~60fps for smoother scratching
            
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """
        Handle mouse release events to end dragging and restore state.

        Args:
            event: The QMouseEvent instance.
        """
        if event.button() == Qt.MouseButton.LeftButton and self.is_dragging:
            self.is_dragging = False
            self.is_outer_ring = False
            self.last_y = None
            
            # Restore playing state if it was playing before drag
            if self._was_playing:
                self._is_playing = True
                if not self.timer.isActive():
                    self.timer.start()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def rotate(self):
        """
        Rotate the turntable with smoother animation if playing and not dragging.
        """
        if self._is_playing and not self.is_dragging:
            self.angle = (self.angle + self.rotation_speed) % 360.0
            self.update()

    def _emit_seek_position(self):
        """
        Emit the pending seek position after debounce.
        """
        if self.pending_seek_position is not None:
            self.positionScrubbed.emit(self.pending_seek_position)
            self.pending_seek_position = None 