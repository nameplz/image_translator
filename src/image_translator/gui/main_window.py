from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from image_translator.domain.job import JobSnapshot
from image_translator.gui.controllers import MainWindowState


class MainWindow(QMainWindow):
    def __init__(self, state: MainWindowState | None = None) -> None:
        super().__init__()
        self._state = state or MainWindowState()

        self.open_action = self._create_action("openAction", "Open")
        self.run_action = self._create_action("runAction", "Run")
        self.cancel_action = self._create_action("cancelAction", "Cancel")
        self.output_path_action = self._create_action("outputPathAction", "Output Path")
        self.save_as_action = self._create_action("saveAsAction", "Save As")
        self.settings_action = self._create_action("settingsAction", "Settings")

        self.output_path_label = QLabel()
        self.output_path_label.setObjectName("outputPathLabel")
        self.stage_label = QLabel()
        self.stage_label.setObjectName("stageLabel")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")

        self.setWindowTitle("Image Translator")
        self.resize(1180, 760)
        self._build_toolbar()
        self._build_body()
        self._connect_placeholder_actions()
        self._refresh_from_state()

    def set_input_image(self, path: str) -> None:
        self._state = self._state.with_input_image(path)
        self.status_label.setText(f"Selected image: {path}")
        self._refresh_actions()

    def set_output_path(self, path: str) -> None:
        self._state = self._state.with_output_path(path)
        self._refresh_from_state()

    def display_snapshot(self, snapshot: JobSnapshot) -> None:
        self._state = self._state.with_snapshot(snapshot)
        self._refresh_from_state()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.run_action)
        toolbar.addAction(self.cancel_action)
        toolbar.addSeparator()
        toolbar.addAction(self.output_path_action)
        toolbar.addAction(self.save_as_action)
        toolbar.addSeparator()
        toolbar.addAction(self.settings_action)
        self.addToolBar(toolbar)

    def _build_body(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        splitter.setObjectName("mainSplitter")
        splitter.addWidget(self._build_comparison_tabs(splitter))
        splitter.addWidget(self._build_review_tabs(splitter))
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, 1)
        layout.addWidget(self._build_bottom_bar(central))
        self.setCentralWidget(central)

    def _build_comparison_tabs(self, parent: QWidget) -> QTabWidget:
        tabs = QTabWidget(parent)
        tabs.setObjectName("imageComparisonTabs")
        tabs.addTab(self._placeholder_page("Original image preview", tabs), "Original")
        tabs.addTab(self._placeholder_page("OCR region overlay", tabs), "OCR Overlay")
        tabs.addTab(self._placeholder_page("Inpainted preview", tabs), "Inpainted")
        tabs.addTab(self._placeholder_page("Rendered result preview", tabs), "Result")
        return tabs

    def _build_review_tabs(self, parent: QWidget) -> QTabWidget:
        tabs = QTabWidget(parent)
        tabs.setObjectName("reviewTabs")
        tabs.setMinimumWidth(300)
        tabs.addTab(self._placeholder_page("No region selected", tabs), "Region Inspector")
        tabs.addTab(self._placeholder_page("Review queue is empty", tabs), "Review Queue")
        tabs.addTab(self._placeholder_page("No revision plan", tabs), "Revision Plan")
        return tabs

    def _build_bottom_bar(self, parent: QWidget) -> QFrame:
        frame = QFrame(parent)
        frame.setObjectName("progressStatusBar")
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(12)

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedWidth(180)

        self.status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.output_path_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        layout.addWidget(self.stage_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label, 1)
        layout.addWidget(self.output_path_label, 1)
        return frame

    def _connect_placeholder_actions(self) -> None:
        self.open_action.triggered.connect(self._choose_input_image)
        self.output_path_action.triggered.connect(self._choose_output_path)
        self.run_action.triggered.connect(
            lambda: self.status_label.setText("Workflow worker is not configured.")
        )
        self.cancel_action.triggered.connect(
            lambda: self.status_label.setText("Cancellation is not active.")
        )
        self.save_as_action.triggered.connect(
            lambda: self.status_label.setText("Save As is available after export approval.")
        )
        self.settings_action.triggered.connect(
            lambda: self.status_label.setText("Settings are not configured.")
        )

    def _choose_input_image(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp);;All files (*)",
        )
        if path:
            self.set_input_image(path)

    def _choose_output_path(self) -> None:
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Output Path",
            "",
            "PNG image (*.png);;JPEG image (*.jpg *.jpeg);;WebP image (*.webp)",
        )
        if path:
            self.set_output_path(path)

    def _refresh_from_state(self) -> None:
        self.stage_label.setText(f"Stage: {self._state.stage_text}")
        self.progress_bar.setValue(self._state.progress_percent)
        self.status_label.setText(self._state.status_text)
        self.output_path_label.setText(self._state.output_path_text)
        self._refresh_actions()

    def _refresh_actions(self) -> None:
        self.run_action.setEnabled(self._state.run_enabled)
        self.cancel_action.setEnabled(self._state.cancel_enabled)
        self.save_as_action.setEnabled(self._state.save_as_enabled)

    @staticmethod
    def _create_action(object_name: str, text: str) -> QAction:
        action = QAction(text)
        action.setObjectName(object_name)
        return action

    @staticmethod
    def _placeholder_page(message: str, parent: QWidget) -> QWidget:
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        label = QLabel(message, page)
        label.setObjectName("placeholderLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        return page


__all__ = ["MainWindow"]
