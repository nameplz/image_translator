from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from image_translator.domain.ocr import NormalizedTextRegion
from image_translator.domain.quality import ApprovalStatus, QualityIssue, RegionReview
from image_translator.domain.render import RenderPlan
from image_translator.domain.translation import TranslationCandidate, TranslationResult

_APPROVED_STATUSES = {
    ApprovalStatus.approved_automatic,
    ApprovalStatus.approved_user,
    ApprovalStatus.approved_forced,
}


@dataclass(frozen=True, slots=True)
class ReviewRegionState:
    region: NormalizedTextRegion
    primary_ocr_text: str
    approved_ocr_text: str
    secondary_ocr_text: str | None = None
    translation_candidates: tuple[TranslationCandidate, ...] = ()
    approved_translation: TranslationResult | None = None
    review: RegionReview | None = None
    issues: tuple[QualityIssue, ...] = ()
    render_plan: RenderPlan | None = None
    approval_status: ApprovalStatus = ApprovalStatus.pending


class ReviewQueueWidget(QWidget):
    region_selected: ClassVar[Signal] = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._states: tuple[ReviewRegionState, ...] = ()

        self.queue_list = QListWidget(self)
        self.queue_list.setObjectName("reviewQueueList")
        self.queue_list.currentItemChanged.connect(self._handle_current_item_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.queue_list)

    def set_regions(self, states: tuple[ReviewRegionState, ...]) -> None:
        self._states = states
        self._refresh_rows(selected_region_id=None)

    def select_region(self, region_id: str | None) -> None:
        self._refresh_rows(selected_region_id=region_id)

    def visible_region_ids(self) -> tuple[str, ...]:
        return tuple(
            str(self.queue_list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.queue_list.count())
        )

    def _refresh_rows(self, *, selected_region_id: str | None) -> None:
        self.queue_list.blockSignals(True)
        self.queue_list.clear()
        for state in self._reviewable_states():
            item = QListWidgetItem(_format_queue_item(state))
            item.setData(Qt.ItemDataRole.UserRole, state.region.region_id)
            self.queue_list.addItem(item)
            if state.region.region_id == selected_region_id:
                item.setSelected(True)
                self.queue_list.setCurrentItem(item)
        self.queue_list.blockSignals(False)

    def _reviewable_states(self) -> tuple[ReviewRegionState, ...]:
        return tuple(
            state
            for state in self._states
            if state.approval_status not in _APPROVED_STATUSES
        )

    def _handle_current_item_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        self.region_selected.emit(str(current.data(Qt.ItemDataRole.UserRole)))


class RegionInspectorWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state: ReviewRegionState | None = None

        self.region_id_value = QLabel("none", self)
        self.region_id_value.setObjectName("regionIdValue")
        self.writing_mode_value = QLabel("none", self)
        self.writing_mode_value.setObjectName("writingModeValue")
        self.reading_order_value = QLabel("none", self)
        self.reading_order_value.setObjectName("readingOrderValue")
        self.text_role_value = QLabel("none", self)
        self.text_role_value.setObjectName("textRoleValue")
        self.primary_ocr_value = _read_only_text("primaryOcrValue")
        self.secondary_ocr_value = _read_only_text("secondaryOcrValue")
        self.approved_ocr_value = _read_only_text("approvedOcrValue")
        self.translation_candidates_value = _read_only_text("translationCandidatesValue")
        self.approved_translation_value = _read_only_text("approvedTranslationValue")
        self.review_value = _read_only_text("reviewValue")
        self.issues_value = _read_only_text("issuesValue")
        self.render_plan_value = _read_only_text("renderPlanValue")

        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow("Region", self.region_id_value)
        form.addRow("Writing mode", self.writing_mode_value)
        form.addRow("Reading order", self.reading_order_value)
        form.addRow("Text role", self.text_role_value)
        form.addRow("Primary OCR", self.primary_ocr_value)
        form.addRow("Secondary OCR", self.secondary_ocr_value)
        form.addRow("Approved OCR", self.approved_ocr_value)
        form.addRow("Translation candidates", self.translation_candidates_value)
        form.addRow("Approved translation", self.approved_translation_value)
        form.addRow("Reviewer", self.review_value)
        form.addRow("Issues", self.issues_value)
        form.addRow("RenderPlan", self.render_plan_value)

    def show_region(self, state: ReviewRegionState | None) -> None:
        self._state = state
        if state is None:
            self._clear()
            return
        region = state.region
        reading_order = region.reading_order
        self.region_id_value.setText(region.region_id)
        self.writing_mode_value.setText(region.writing_mode.value)
        self.reading_order_value.setText(
            f"{reading_order.page_index}.{reading_order.group_index}.{reading_order.item_index}"
        )
        self.text_role_value.setText(region.text_role.value)
        self.primary_ocr_value.setPlainText(state.primary_ocr_text)
        self.secondary_ocr_value.setPlainText(state.secondary_ocr_text or "none")
        self.approved_ocr_value.setPlainText(state.approved_ocr_text)
        self.translation_candidates_value.setPlainText(_format_candidates(state))
        self.approved_translation_value.setPlainText(_format_approved_translation(state))
        self.review_value.setPlainText(_format_review(state.review))
        self.issues_value.setPlainText(_format_issues(state.issues))
        self.render_plan_value.setPlainText(_format_render_plan(state.render_plan))

    def _clear(self) -> None:
        self.region_id_value.setText("none")
        self.writing_mode_value.setText("none")
        self.reading_order_value.setText("none")
        self.text_role_value.setText("none")
        for field in (
            self.primary_ocr_value,
            self.secondary_ocr_value,
            self.approved_ocr_value,
            self.translation_candidates_value,
            self.approved_translation_value,
            self.review_value,
            self.issues_value,
            self.render_plan_value,
        ):
            field.setPlainText("none")


def _read_only_text(object_name: str) -> QPlainTextEdit:
    field = QPlainTextEdit()
    field.setObjectName(object_name)
    field.setReadOnly(True)
    field.setMaximumBlockCount(200)
    field.setFixedHeight(58)
    return field


def _format_queue_item(state: ReviewRegionState) -> str:
    severity = _highest_severity(state.issues)
    action = next(
        (
            issue.recommended_action
            for issue in state.issues
            if issue.recommended_action is not None and not issue.resolved
        ),
        "review required",
    )
    return (
        f"{state.region.region_id} | severity={severity} | "
        f"status={state.approval_status.value} | action={action}"
    )


def _format_candidates(state: ReviewRegionState) -> str:
    if not state.translation_candidates:
        return "none"
    return "\n".join(
        f"{candidate.candidate_id}: attempt={candidate.attempt}; "
        f"text={candidate.translated_text}"
        for candidate in state.translation_candidates
    )


def _format_approved_translation(state: ReviewRegionState) -> str:
    if state.approved_translation is None:
        return "none"
    return (
        f"{state.approved_translation.approval_status}: "
        f"{state.approved_translation.approved_translated_text}"
    )


def _format_review(review: RegionReview | None) -> str:
    if review is None:
        return "none"
    scores = review.rubric_scores
    return (
        f"decision={review.decision}; total={review.total_score:g}; "
        f"semantic={scores.semantic_fidelity:g}; "
        f"completeness={scores.completeness:g}; "
        f"voice={scores.character_voice:g}; "
        f"evidence={review.evidence_summary}; "
        f"instruction={review.improvement_instruction or 'none'}"
    )


def _format_issues(issues: tuple[QualityIssue, ...]) -> str:
    unresolved = tuple(issue for issue in issues if not issue.resolved)
    if not unresolved:
        return "none"
    return "\n".join(
        f"{issue.severity.value}:{issue.issue_code}: {issue.summary}; "
        f"action={issue.recommended_action or 'none'}"
        for issue in unresolved
    )


def _format_render_plan(plan: RenderPlan | None) -> str:
    if plan is None:
        return "none"
    return (
        f"region={plan.region_id}; text={plan.translated_text}; "
        f"font={plan.style.font_family}; size={plan.style.size}; "
        f"mode={plan.style.writing_mode.value}; "
        f"overflow={plan.overflow_policy.value}; "
        f"evidence={', '.join(plan.source_style_evidence) or 'none'}"
    )


def _highest_severity(issues: tuple[QualityIssue, ...]) -> str:
    rank = {"info": 1, "warning": 2, "error": 3, "critical": 4}
    unresolved = tuple(issue.severity.value for issue in issues if not issue.resolved)
    if not unresolved:
        return "none"
    return max(unresolved, key=lambda severity: rank[severity])


__all__ = [
    "RegionInspectorWidget",
    "ReviewQueueWidget",
    "ReviewRegionState",
]
