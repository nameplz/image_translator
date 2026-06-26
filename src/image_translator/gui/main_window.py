from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from image_translator.domain.export import ExportEligibilityDecision, FinalImageResult
from image_translator.domain.job import JobDefinition, JobSnapshot, JobStatus
from image_translator.gui.controllers import MainWindowState, ResumeListController
from image_translator.gui.export_controller import ExportController, ExportControllerError
from image_translator.gui.review_panel import (
    RegionInspectorWidget,
    ReviewQueueWidget,
    ReviewRegionState,
)
from image_translator.gui.revision_panel import RevisionPlanPanel, RevisionPreviewState
from image_translator.gui.settings_dialog import (
    SettingsDialog,
    SettingsDialogState,
    default_settings_dialog_state,
)
from image_translator.gui.viewer import ImageOverlayViewer
from image_translator.gui.workers import ImageTranslationUseCase, ImageTranslationWorker


class MainWindow(QMainWindow):
    def __init__(
        self,
        state: MainWindowState | None = None,
        *,
        use_case: ImageTranslationUseCase | None = None,
        settings_state: SettingsDialogState | None = None,
        export_controller: ExportController | None = None,
        resume_controller: ResumeListController | None = None,
    ) -> None:
        super().__init__()
        self._state = state or MainWindowState()
        self._use_case = use_case
        self._settings_state = settings_state or default_settings_dialog_state()
        self._export_controller = export_controller or ExportController(
            overwrite_confirmation=self._confirm_overwrite,
            force_reason_request=self._request_force_export_reason,
        )
        self._resume_controller = resume_controller or ResumeListController()
        self._worker: ImageTranslationWorker | None = None
        self._review_regions: tuple[ReviewRegionState, ...] = ()
        self._selected_region_id: str | None = None
        self._status_override: str | None = None

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
        self.overlay_viewer = ImageOverlayViewer(self)
        self.region_inspector = RegionInspectorWidget(self)
        self.review_queue = ReviewQueueWidget(self)
        self.revision_panel = RevisionPlanPanel(self)

        self.setWindowTitle("Image Translator")
        self.resize(1180, 760)
        self._build_toolbar()
        self._build_body()
        self._connect_placeholder_actions()
        self._refresh_from_state()

    def set_input_image(self, path: str) -> None:
        self._state = self._state.with_input_image(path)
        self._export_controller.set_input_path(path)
        self.status_label.setText(f"Selected image: {path}")
        self._refresh_actions()

    def set_output_path(self, path: str) -> None:
        self._state = self._state.with_output_path(path)
        self._export_controller.set_output_path(path)
        self._status_override = None
        self._refresh_from_state()

    def set_review_before_save_mode(self, enabled: bool) -> None:
        self._export_controller.set_review_before_save(enabled)
        self._refresh_from_state()

    def display_snapshot(self, snapshot: JobSnapshot) -> None:
        self._state = self._state.with_snapshot(snapshot)
        self._status_override = None
        self._refresh_from_state()

    def set_final_image_result(self, result: FinalImageResult) -> None:
        self._export_controller.set_final_image_result(result)
        self._status_override = (
            None
            if self._export_controller.normal_save_allowed_if_result_known
            else self._export_controller.export_blocking_text()
        )
        self._refresh_from_state()

    def set_review_regions(self, regions: tuple[ReviewRegionState, ...]) -> None:
        self._review_regions = regions
        issues = tuple(issue for region in regions for issue in region.issues)
        self.overlay_viewer.set_regions(
            tuple(region_state.region for region_state in regions),
            issues,
        )
        self.review_queue.set_regions(regions)
        if self._selected_region_id is not None:
            self.select_region(self._selected_region_id)

    def select_region(self, region_id: str) -> None:
        self._selected_region_id = region_id
        self.overlay_viewer.select_region(region_id)
        self.review_queue.select_region(region_id)
        self.region_inspector.show_region(self._review_region_by_id(region_id))

    def display_revision_preview_state(
        self,
        request_id: int,
        state: RevisionPreviewState,
    ) -> None:
        self.revision_panel.display_preview_state(request_id=request_id, state=state)

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
        tabs.addTab(self.overlay_viewer, "OCR Overlay")
        tabs.addTab(self._placeholder_page("Inpainted preview", tabs), "Inpainted")
        tabs.addTab(self._placeholder_page("Rendered result preview", tabs), "Result")
        return tabs

    def _build_review_tabs(self, parent: QWidget) -> QTabWidget:
        tabs = QTabWidget(parent)
        tabs.setObjectName("reviewTabs")
        tabs.setMinimumWidth(300)
        tabs.addTab(self.region_inspector, "Region Inspector")
        tabs.addTab(self.review_queue, "Review Queue")
        tabs.addTab(self.revision_panel, "Revision Plan")
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
        self.run_action.triggered.connect(self._start_translation)
        self.cancel_action.triggered.connect(self._cancel_translation)
        self.save_as_action.triggered.connect(self._prepare_save_as_request)
        self.settings_action.triggered.connect(self._open_settings_dialog)
        self.overlay_viewer.selected_region_changed.connect(self.select_region)
        self.review_queue.region_selected.connect(self.select_region)

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

    def _start_translation(self) -> None:
        resumable = self._resume_controller.resumable_checkpoints()
        if resumable:
            self.status_label.setText(
                f"{len(resumable)} resumable checkpoint(s) available before new job start."
            )
        if self._use_case is None:
            self.status_label.setText("Workflow worker is not configured.")
            return
        if self._state.input_image_path is None:
            self.status_label.setText("Select an image before running.")
            return
        if not self._settings_allow_run():
            self.status_label.setText(
                "Visual mode requires image transmission consent before running."
            )
            return
        if not self._output_path_allows_run():
            self.status_label.setText("Choose an output path or enable review-before-save mode.")
            return
        if self._worker is not None:
            self.status_label.setText("Workflow is already running.")
            return

        job = self._create_job_definition()
        worker = ImageTranslationWorker(job=job, use_case=self._use_case)
        worker.snapshot_received.connect(self.display_snapshot)
        worker.finished.connect(self._clear_finished_worker)
        self._worker = worker
        self.display_snapshot(
            JobSnapshot(
                job_id=job.job_id,
                status=JobStatus.preparing,
                progress=0.0,
                stage="prepare",
                message="Starting workflow",
                can_cancel=True,
            )
        )
        worker.start()

    def _cancel_translation(self) -> None:
        if self._worker is None or not self._state.cancel_enabled:
            self.status_label.setText("Cancellation is not active.")
            return
        self._state = self._state.with_cancelling()
        self._refresh_from_state()
        self._worker.cancel()

    def _clear_finished_worker(self) -> None:
        worker = self.sender()
        if worker is self._worker:
            self._worker.deleteLater()
            self._worker = None

    def _prepare_save_as_request(self) -> None:
        if self._state.output_path is None:
            self._choose_output_path()
        try:
            self._export_controller.prepare_export_request(force=False)
        except ExportControllerError as exc:
            self._status_override = exc.user_message
        else:
            self._status_override = "Save request passed export gate; background save is pending."
        self._refresh_from_state()

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self._settings_state, self)
        dialog.exec()

    def _confirm_overwrite(self, output_path: Path) -> bool:
        result = QMessageBox.question(
            self,
            "Confirm overwrite",
            f"Replace existing output file?\n{output_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result is QMessageBox.StandardButton.Yes

    def _request_force_export_reason(
        self,
        decision: ExportEligibilityDecision,
    ) -> str | None:
        text, accepted = QInputDialog.getText(
            self,
            "Forced export reason",
            f"Normal export is blocked: {', '.join(decision.reason_codes)}\nReason:",
        )
        return text if accepted else None

    def _create_job_definition(self) -> JobDefinition:
        if self._state.input_image_path is None:
            raise RuntimeError("input image path is required before starting a workflow")
        provider_settings = self._settings_state.provider_settings
        return JobDefinition(
            job_id=f"gui-job-{uuid4().hex}",
            project_id="default-project",
            input_path=self._state.input_image_path,
            requested_output_path=self._export_controller.requested_output_path,
            source_language="ja",
            target_language="ko",
            provider_selection=(
                self._settings_state.primary_ocr_provider_id,
                provider_settings.translator.provider_id,
                provider_settings.reviewer.provider_id,
            ),
            fallback_order=tuple(
                f"{fallback.role.value}:{fallback.provider_id}"
                for fallback in provider_settings.fallback_order
            ),
            visual_mode=provider_settings.visual_mode_default,
            image_transmission_consent=(
                provider_settings.image_transmission_consent_default
            ),
            processing_profile="balanced",
        )

    def _refresh_from_state(self) -> None:
        self.stage_label.setText(f"Stage: {self._state.stage_text}")
        self.progress_bar.setValue(self._state.progress_percent)
        self.status_label.setText(self._status_override or self._state.status_text)
        self.output_path_label.setText(self._state.output_path_text)
        self._refresh_actions()

    def _refresh_actions(self) -> None:
        self.run_action.setEnabled(
            self._state.run_enabled
            and self._settings_allow_run()
            and self._output_path_allows_run()
        )
        self.cancel_action.setEnabled(self._state.cancel_enabled)
        self.save_as_action.setEnabled(
            self._state.save_as_enabled
            and self._export_controller.normal_save_allowed_if_result_known
        )

    def _settings_allow_run(self) -> bool:
        settings = self._settings_state.provider_settings
        return (
            not settings.visual_mode_default
            or settings.image_transmission_consent_default
        )

    def _output_path_allows_run(self) -> bool:
        return (
            self._export_controller.state.review_before_save
            or self._export_controller.requested_output_path is not None
        )

    def _review_region_by_id(self, region_id: str) -> ReviewRegionState | None:
        return next(
            (
                region_state
                for region_state in self._review_regions
                if region_state.region.region_id == region_id
            ),
            None,
        )

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
