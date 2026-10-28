from PyQt6.QtWidgets import (QApplication, QWidget, QTextEdit, QVBoxLayout, QGraphicsDropShadowEffect, 
                             QSizeGrip, QHBoxLayout, QScrollArea, QLabel, QFrame)
from PyQt6.QtCore import Qt, QEvent, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette, QCursor

from ctypes import c_void_p
import configparser
import os
import time

# macOS: Make window visible on all desktops (Spaces)
try:
    from AppKit import NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorStationary
    import objc
    HAS_APPKIT = True
except ImportError:
    HAS_APPKIT = False


def calculate_overlay_geometry(
    screen_x,
    screen_y,
    screen_width,
    screen_height,
    requested_width,
    requested_height,
    bottom_margin,
    position="bottom_center",
):
    available_width = max(1, screen_width - 40)
    available_height = max(1, screen_height - 40)
    minimum_width = min(480, available_width)
    minimum_height = min(220, available_height)
    width = min(max(requested_width, minimum_width), available_width)
    height = min(max(requested_height, minimum_height), available_height)
    horizontal_margin = 20
    if position == "bottom_left":
        x = screen_x + horizontal_margin
    elif position == "bottom_right":
        x = screen_x + screen_width - width - horizontal_margin
    else:
        x = screen_x + (screen_width - width) // 2
    y = screen_y + screen_height - height - max(0, bottom_margin)
    y = max(screen_y + 20, y)
    return x, y, width, height


def should_show_translation(text):
    return bool(text) and text != "(translating...)"


# Width in pixels of the resize zone along every window edge. The outer 12 px
# of the window is fully transparent and does not reliably receive mouse
# events on Windows, so the zone must extend past it onto the visible panel.
RESIZE_MARGIN = 20


def detect_resize_edges(x, y, width, height, margin=RESIZE_MARGIN):
    """Return the set of window edges the point (x, y) is close to.

    Possible members: "left", "right", "top", "bottom". A corner returns
    two members (e.g. {"right", "bottom"}); the interior returns an empty set.
    """
    edges = set()
    if x <= margin:
        edges.add("left")
    elif x >= width - margin:
        edges.add("right")
    if y <= margin:
        edges.add("top")
    elif y >= height - margin:
        edges.add("bottom")
    return edges


def persist_window_size(config_path, width, height):
    """Write the user-chosen overlay size back to config.ini [display]."""
    parser = configparser.ConfigParser()
    parser.read(config_path)
    if not parser.has_section("display"):
        parser.add_section("display")
    parser.set("display", "window_width", str(int(width)))
    parser.set("display", "window_height", str(int(height)))
    with open(config_path, "w") as f:
        parser.write(f)


class LogItem(QFrame):
    """A widget representing a single chunk of transcription/translation"""
    def __init__(
        self,
        chunk_id,
        timestamp,
        original_text,
        translated_text="",
        original_font_size=16,
        translation_font_size=24,
    ):
        super().__init__()
        self.chunk_id = chunk_id
        self.timestamp = timestamp
        self.original_font_size = original_font_size
        self.translation_font_size = translation_font_size
        
        # Style
        self.setStyleSheet("background-color: transparent;")
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 20)
        self.layout.setSpacing(6)
        self.setLayout(self.layout)
        
        # Original Text Label
        self.original_label = QLabel(f"[{timestamp}] {original_text}")
        self.original_label.setWordWrap(True)
        self.original_label.setStyleSheet(
            "color: rgba(242, 245, 255, 210); font-family: 'Segoe UI', Arial; "
            f"font-size: {self.original_font_size}px; font-weight: 500;"
        )
        self.layout.addWidget(self.original_label)
        
        # Translated Text Label
        self.translated_label = QLabel("")
        self.translated_label.setWordWrap(True)
        self.layout.addWidget(self.translated_label)
        self.update_translated(translated_text)
        
    def update_translated(self, text):
        # Pending translation stays hidden so stable source text can lead visually.
        has_text = should_show_translation(text)
        self.translated_label.setVisible(has_text)
        if not has_text:
            self.translated_label.setText("")
            return

        if text == "[Translation Failed]":
            self.translated_label.setStyleSheet(
                "color: #ffb4ab; font-family: 'Microsoft YaHei UI', 'Segoe UI', Arial; "
                f"font-size: {max(16, self.translation_font_size - 4)}px; font-weight: 700;"
            )
            self.translated_label.setText(text)
        else:
            self.translated_label.setStyleSheet(
                "color: #ffffff; font-family: 'Microsoft YaHei UI', 'Segoe UI', Arial; "
                f"font-size: {self.translation_font_size}px; "
                "font-weight: 700; line-height: 132%;"
            )
            self.translated_label.setText(text)

    def update_original(self, text):
        self.original_label.setText(f"[{self.timestamp}] {text}")

class ResizeHandle(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = parent
        self.setText("◢")
        self.setToolTip("Drag to resize (any window edge works too)")
        self.setStyleSheet(
            "QLabel { color: rgba(255, 255, 255, 150); font-size: 16px; }"
            "QLabel:hover { color: rgba(255, 255, 255, 240); }"
        )
        self.setFixedSize(24, 24)
        self.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        
        self.startPos = None
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.startPos = event.globalPosition().toPoint()
            event.accept()
            
    def mouseMoveEvent(self, event):
        if self.startPos:
            delta = event.globalPosition().toPoint() - self.startPos
            new_width = max(self.parent_window.minimumWidth(), self.parent_window.width() + delta.x())
            new_height = max(self.parent_window.minimumHeight(), self.parent_window.height() + delta.y())
            
            self.parent_window.resize(new_width, new_height)
            self.startPos = event.globalPosition().toPoint()
            event.accept()
            
    def mouseReleaseEvent(self, event):
        if self.startPos is not None:
            self.startPos = None
            self.parent_window._on_user_resized()

class OverlayWindow(QWidget):
    stop_requested = pyqtSignal()
    size_persisted = pyqtSignal(int, int)

    def __init__(
        self,
        display_duration=None,
        window_width=1000,
        window_height=320,
        max_visible_items=3,
        bottom_margin=48,
        position="bottom_center",
        original_font_size=16,
        translation_font_size=24,
        panel_opacity=118,
        auto_hide_controls=True,
    ):
        super().__init__()
        # display_duration is not really used in log mode, but kept for compatibility
        self.window_width = window_width
        self.window_height = window_height
        self.max_visible_items = max_visible_items
        self.bottom_margin = max(0, bottom_margin)
        self.position = position
        self.original_font_size = max(10, original_font_size)
        self.translation_font_size = max(12, translation_font_size)
        self.panel_opacity = min(max(panel_opacity, 35), 230)
        self.auto_hide_controls = auto_hide_controls
        
        self.initUI()
        self.oldPos = self.pos()

    def showEvent(self, event):
        """Called when window is shown - set all-spaces behavior here"""
        super().showEvent(event)
        if HAS_APPKIT:
            self._set_all_spaces()
    
    def _set_all_spaces(self):
        """Make window appear on all macOS Spaces/Desktops"""
        try:
            # Get the native NSWindow from Qt's winId
            win_id = int(self.winId())
            ns_view = objc.objc_object(c_void_p=c_void_p(win_id))
            ns_window = ns_view.window()
            ns_window.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary
            )
            print("Window set to appear on all Spaces")
        except Exception as e:
            print(f"Could not set all-spaces behavior: {e}")

    def initUI(self):
        # Window flags for transparency and staying on top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        # Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 10)
        self.setLayout(layout)
        
        # SCROLL AREA
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        # Transparent scroll area
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: transparent; }
            QScrollBar:vertical { width: 0px; }
        """)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Container for LogItems
        self.container = QFrame()
        self.container.setObjectName("subtitlePanel")
        self.container.setStyleSheet(f"""
            QFrame#subtitlePanel {{
                background-color: rgba(8, 10, 14, {self.panel_opacity});
                border: 1px solid rgba(255, 255, 255, 34);
                border-radius: 8px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self.container)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 105))
        self.container.setGraphicsEffect(shadow)
        self.container_layout = QVBoxLayout()
        self.container_layout.setContentsMargins(14, 12, 14, 12)
        self.container_layout.setSpacing(0)
        # Allocate alignment to top so items stack from top
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.container.setLayout(self.container_layout)
        
        self.scroll_area.setWidget(self.container)
        layout.addWidget(self.scroll_area)
        
        # Bottom control bar keeps a fixed footprint so hover does not shift subtitles.
        self.control_bar = QFrame()
        self.control_bar.setFixedHeight(34)
        self.control_bar.setStyleSheet("background: transparent; border: none;")
        grip_layout = QHBoxLayout(self.control_bar)
        grip_layout.setContentsMargins(0, 0, 0, 0)
        grip_layout.setSpacing(8)
        
        # Save Button
        from PyQt6.QtWidgets import QPushButton
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setToolTip("Save the transcript shown so far to the transcripts folder")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setFixedWidth(80)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(10, 12, 16, 95);
                color: white;
                border-radius: 6px;
                padding: 5px;
                border: 1px solid rgba(255, 255, 255, 40);
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 72);
            }
        """)
        self.save_btn.clicked.connect(self._save_transcript)
        
        grip_layout.addWidget(self.save_btn)
        
        # Stop Button
        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setToolTip("Stop Translator")
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setFixedSize(30, 30)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(243, 139, 168, 120);
                color: white;
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 35);
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(243, 139, 168, 200);
            }
        """)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        grip_layout.addWidget(self.stop_btn)
        
        grip_layout.addStretch()
        
        # Visual Grip Indicator
        self.grip_label = ResizeHandle(self)
        grip_layout.addWidget(self.grip_label)
        
        layout.addWidget(self.control_bar)

        # The resize grip stays visible at all times so the resize affordance
        # is discoverable; only the buttons participate in auto-hide.
        self._control_widgets = [self.save_btn, self.stop_btn]
        self._controls_hide_timer = QTimer(self)
        self._controls_hide_timer.setSingleShot(True)
        self._controls_hide_timer.timeout.connect(self._hide_controls)
        if self.auto_hide_controls:
            self._hide_controls()
        
        # Keep the subtitle surface inside the usable desktop area.
        screen = QApplication.primaryScreen().availableGeometry()
        x, y, width, height = calculate_overlay_geometry(
            screen.x(),
            screen.y(),
            screen.width(),
            screen.height(),
            self.window_width,
            self.window_height,
            self.bottom_margin,
            self.position,
        )
        # Same floor as calculate_overlay_geometry, so edge/grip resizing
        # cannot shrink the window below a usable size.
        self.setMinimumSize(
            min(480, max(1, screen.width() - 40)),
            min(220, max(1, screen.height() - 40)),
        )
        self.resize(width, height)

        # Position: centered horizontally and raised slightly above the taskbar.
        self.move(x, y)
        
        # Data storage: list of (chunk_id, widget) inclusive
        self.items = [] # Sorted by chunk_id
        
        # History for saving (list of dicts)
        self.transcript_data = {} # chunk_id -> {timestamp, original, translated}
        
        # State
        self.is_moving = False
        self._resize_edges = set()
        self._resize_start_geometry = None
        self._resize_start_pos = None

        # Enable mouse tracking for cursor update without click
        self.setMouseTracking(True)
        # Hover moves over these children must reach the window too, or the
        # resize cursor would never appear over the visible panel edges.
        for child in (self.scroll_area.viewport(), self.container, self.control_bar):
            child.setMouseTracking(True)
            child.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseMove and not event.buttons():
            pos = self.mapFromGlobal(event.globalPosition().toPoint())
            edges = detect_resize_edges(pos.x(), pos.y(), self.width(), self.height())
            self.setCursor(self._cursor_for_edges(edges))
        return super().eventFilter(obj, event)

    def update_text(self, chunk_id, original_text, translated_text):
        """Append new text or update existing text"""
        print(f"[Overlay] Received update for #{chunk_id}: {original_text} -> {translated_text}")
        
        # Update data store
        if chunk_id not in self.transcript_data:
            self.transcript_data[chunk_id] = {
                'timestamp': time.strftime("%H:%M:%S"),
                'original': original_text,
                'translated': translated_text
            }
        else:
            if original_text:
                self.transcript_data[chunk_id]['original'] = original_text
            if translated_text:
                self.transcript_data[chunk_id]['translated'] = translated_text
        
        # Check if widget exists
        existing_widget = None
        for cid, widget in self.items:
            if cid == chunk_id:
                existing_widget = widget
                break
        
        if existing_widget:
            # Update existing
            if original_text:
                existing_widget.update_original(original_text)
            
            if translated_text:
                existing_widget.update_translated(translated_text)
                
            print(f"[Overlay] Updated existing widget #{chunk_id}")
        else:
            # Insert new widget in order
            timestamp = self.transcript_data[chunk_id]['timestamp']
            new_widget = LogItem(
                chunk_id,
                timestamp,
                original_text,
                translated_text,
                original_font_size=self.original_font_size,
                translation_font_size=self.translation_font_size,
            )
            
            # Find insertion point
            insert_idx = len(self.items)
            for i, (cid, w) in enumerate(self.items):
                if cid > chunk_id:
                    insert_idx = i
                    break
            
            self.items.insert(insert_idx, (chunk_id, new_widget))
            self.container_layout.insertWidget(insert_idx, new_widget)
            print(f"[Overlay] Inserted new widget #{chunk_id} at index {insert_idx}")
            
            # Scroll to bottom
            QTimer.singleShot(10, self._scroll_to_bottom)
            self._trim_visible_items()

    def _scroll_to_bottom(self):
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _trim_visible_items(self):
        while len(self.items) > self.max_visible_items:
            old_chunk_id, old_widget = self.items.pop(0)
            self.container_layout.removeWidget(old_widget)
            old_widget.deleteLater()
            print(f"[Overlay] Hid old widget #{old_chunk_id}")

    def _save_transcript(self):
        """Save history to file"""
        import os
        if not self.transcript_data:
            print("[Overlay] Nothing to save.")
            return

        os.makedirs("transcripts", exist_ok=True)
        filename = f"transcripts/transcript_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        
        # Sort by chunk_id
        sorted_ids = sorted(self.transcript_data.keys())
        
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"Transcript saved at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("="*50 + "\n\n")
                for cid in sorted_ids:
                    data = self.transcript_data[cid]
                    f.write(f"[{data['timestamp']}] (ID: {cid})\nOriginal: {data['original']}\nTranslation: {data['translated']}\n{'-'*30}\n")
            
            print(f"[Overlay] Saved to {filename}")
            # Visual feedback on button
            original_text = self.save_btn.text()
            self.save_btn.setText("Saved!")
            QTimer.singleShot(2000, lambda: self.save_btn.setText(original_text))
            
        except Exception as e:
            print(f"[Overlay] Error saving transcript: {e}")

    def _show_controls(self):
        self._controls_hide_timer.stop()
        for widget in self._control_widgets:
            widget.show()

    def _hide_controls(self):
        if not self.auto_hide_controls:
            return
        cursor_position = self.mapFromGlobal(QCursor.pos())
        if self.isVisible() and self.rect().contains(cursor_position):
            return
        for widget in self._control_widgets:
            widget.hide()

    def enterEvent(self, event):
        if self.auto_hide_controls:
            self._show_controls()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.auto_hide_controls:
            self._controls_hide_timer.start(350)
        super().leaveEvent(event)



    # Window moving and edge resizing logic. A press near any window edge
    # starts a resize; a press anywhere else starts a move.
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            edges = detect_resize_edges(pos.x(), pos.y(), self.width(), self.height())
            if edges:
                self._resize_edges = edges
                self._resize_start_geometry = self.geometry()
                self._resize_start_pos = event.globalPosition().toPoint()
            else:
                self.is_moving = True
                self.oldPos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._resize_edges:
            self._apply_edge_resize(event.globalPosition().toPoint())
            return

        if self.is_moving:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            delta = event.globalPosition().toPoint() - self.oldPos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.oldPos = event.globalPosition().toPoint()
            return

        # Hover: show a resize cursor near edges so resizing is discoverable.
        pos = event.position().toPoint()
        edges = detect_resize_edges(pos.x(), pos.y(), self.width(), self.height())
        self.setCursor(self._cursor_for_edges(edges))

    def mouseReleaseEvent(self, event):
        was_resizing = bool(self._resize_edges)
        self._resize_edges = set()
        self._resize_start_geometry = None
        self._resize_start_pos = None
        self.is_moving = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if was_resizing:
            self._on_user_resized()

    @staticmethod
    def _cursor_for_edges(edges):
        if edges in ({"left"}, {"right"}):
            return Qt.CursorShape.SizeHorCursor
        if edges in ({"top"}, {"bottom"}):
            return Qt.CursorShape.SizeVerCursor
        if edges in ({"left", "top"}, {"right", "bottom"}):
            return Qt.CursorShape.SizeFDiagCursor
        if edges in ({"left", "bottom"}, {"right", "top"}):
            return Qt.CursorShape.SizeBDiagCursor
        return Qt.CursorShape.ArrowCursor

    def _apply_edge_resize(self, global_pos):
        delta = global_pos - self._resize_start_pos
        geo = self._resize_start_geometry
        x, y, width, height = geo.x(), geo.y(), geo.width(), geo.height()
        # Dragging the left or top edge moves that edge and keeps the
        # opposite edge anchored, like a normal window.
        if "right" in self._resize_edges:
            width = max(self.minimumWidth(), geo.width() + delta.x())
        elif "left" in self._resize_edges:
            width = max(self.minimumWidth(), geo.width() - delta.x())
            x = geo.x() + geo.width() - width
        if "bottom" in self._resize_edges:
            height = max(self.minimumHeight(), geo.height() + delta.y())
        elif "top" in self._resize_edges:
            height = max(self.minimumHeight(), geo.height() - delta.y())
            y = geo.y() + geo.height() - height
        self.setGeometry(x, y, width, height)

    def _on_user_resized(self):
        """Remember the size the user dragged to, for this run and the next."""
        self.window_width = self.width()
        self.window_height = self.height()
        config_path = os.path.join(os.path.dirname(__file__), "config.ini")
        try:
            persist_window_size(config_path, self.window_width, self.window_height)
            print(f"[Overlay] Saved window size {self.window_width}x{self.window_height} to config.ini")
        except Exception as e:
            print(f"[Overlay] Could not save window size: {e}")
            return
        self.size_persisted.emit(self.window_width, self.window_height)

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = OverlayWindow()
    window.show()
    # Test update
    window.update_text(1, "Hello world", "")
    QTimer.singleShot(1000, lambda: window.update_text(1, "Hello world", "你好，世界"))
    window.update_text(2, "Sequence test", "")
    sys.exit(app.exec())
