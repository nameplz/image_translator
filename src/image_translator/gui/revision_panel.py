from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from image_translator.domain.revision import (
    RevisionAction,
    RevisionApprovalStatus,
    RevisionPlan,
    RevisionTarget,
)


@dataclass(frozen=True, slots=True)
class RevisionPreviewState:
    status: str
    normalized_instruction: str
    target: RevisionTarget | None = None
    actions: tuple[RevisionAction, ...] = ()
    issue_summaries: tuple[str, ...] = ()


class RevisionPlanPanel(QWidget):
    preview_requested: ClassVar[Signal] = Signal(int, str)
    plan_approval_requested: ClassVar[Signal] = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._latest_request_id = 0
        self._current_plan: RevisionPlan | None = None
        self._current_status: str | None = None

        self.instruction_input = QPlainTextEdit(self)
        self.instruction_input.setObjectName("revisionInstructionInput")
        self.instruction_input.setFixedHeight(64)
        self.plan_id_value = QLabel("none", self)
        self.plan_id_value.setObjectName("revisionPlanIdValue")
        self.target_status_value = QLabel("none", self)
        self.target_status_value.setObjectName("revisionTargetStatusValue")
        self.target_regions_value = QLabel("none", self)
        self.target_regions_value.setObjectName("revisionTargetRegionsValue")
        self.target_scope_value = QLabel("none", self)
        self.target_scope_value.setObjectName("revisionTargetScopeValue")
        self.actions_value = QLabel("none", self)
        self.actions_value.setObjectName("revisionActionsValue")
        self.normalized_instruction_value = _read_only_text("revisionNormalizedInstructionValue")
        self.proposals_value = _read_only_text("revisionProposalsValue")
        self.validation_value = _read_only_text("revisionValidationValue")
        self.warnings_value = _read_only_text("revisionWarningsValue")
        self.project_rule_confirmation = QCheckBox(
            "Confirm project rule change separately",
            self,
        )
        self.project_rule_confirmation.setObjectName("projectRuleConfirmation")
        self.project_rule_confirmation.toggled.connect(self._refresh_approval_state)
        self.status_label = QLabel("No revision plan.", self)
        self.status_label.setObjectName("revisionStatusLabel")
        self.approve_button = QPushButton("Approve Plan", self)
        self.approve_button.setObjectName("approveRevisionPlanButton")
        self.approve_button.clicked.connect(self._request_plan_approval)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.instruction_input)
        form_container = QWidget(self)
        form = QFormLayout(form_container)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow("Plan", self.plan_id_value)
        form.addRow("Target status", self.target_status_value)
        form.addRow("Target regions", self.target_regions_value)
        form.addRow("Scope", self.target_scope_value)
        form.addRow("Actions", self.actions_value)
        form.addRow("Instruction", self.normalized_instruction_value)
        form.addRow("Proposals", self.proposals_value)
        form.addRow("Validation", self.validation_value)
        form.addRow("Warnings", self.warnings_value)
        layout.addWidget(form_container)
        layout.addWidget(self.project_rule_confirmation)
        layout.addWidget(self.status_label)
        layout.addWidget(self.approve_button)

        self._refresh_approval_state()

    def begin_preview(self, instruction: str | None = None) -> int:
        if instruction is not None:
            self.instruction_input.setPlainText(instruction)
        self._latest_request_id += 1
        self._current_plan = None
        self._current_status = None
        self.plan_id_value.setText("pending")
        self.target_status_value.setText("pending")
        self.target_regions_value.setText("pending")
        self.target_scope_value.setText("pending")
        self.actions_value.setText("pending")
        self.normalized_instruction_value.setPlainText(self.instruction_input.toPlainText())
        self.proposals_value.setPlainText("pending")
        self.validation_value.setPlainText("pending")
        self.warnings_value.setPlainText("pending")
        self.project_rule_confirmation.setChecked(False)
        self.project_rule_confirmation.setEnabled(False)
        self.status_label.setText("Revision preview pending.")
        self._refresh_approval_state()
        self.preview_requested.emit(self._latest_request_id, self.instruction_input.toPlainText())
        return self._latest_request_id

    def display_preview_state(self, *, request_id: int, state: RevisionPreviewState) -> None:
        if self._discard_stale_request(request_id):
            return
        self._latest_request_id = max(self._latest_request_id, request_id)
        self._current_status = state.status
        self._current_plan = None
        self.plan_id_value.setText("none")
        self.actions_value.setText(", ".join(action.value for action in state.actions) or "none")
        self.normalized_instruction_value.setPlainText(state.normalized_instruction)
        self.proposals_value.setPlainText("none")
        self.validation_value.setPlainText("none")
        self.warnings_value.setPlainText(_format_state_issues(state))
        self._display_target(state.target)
        self.status_label.setText(_status_message_for_state(state))
        self.project_rule_confirmation.setChecked(False)
        self.project_rule_confirmation.setEnabled(False)
        self._refresh_approval_state()

    def display_plan(self, *, request_id: int, plan: RevisionPlan) -> None:
        if self._discard_stale_request(request_id):
            return
        self._latest_request_id = max(self._latest_request_id, request_id)
        self._current_status = None
        self._display_plan(plan)

    def _discard_stale_request(self, request_id: int) -> bool:
        return request_id < self._latest_request_id

    def _display_plan(self, plan: RevisionPlan) -> None:
        self._current_plan = plan
        self.plan_id_value.setText(plan.plan_id)
        self.actions_value.setText(", ".join(action.value for action in plan.actions) or "none")
        self.normalized_instruction_value.setPlainText(plan.normalized_user_instruction)
        self.proposals_value.setPlainText(_format_proposals(plan))
        self.validation_value.setPlainText(", ".join(plan.required_validation) or "none")
        self.warnings_value.setPlainText("\n".join(plan.warnings) or "none")
        self._display_target(plan.target)
        self.project_rule_confirmation.setChecked(False)
        self.project_rule_confirmation.setEnabled(plan.requires_project_rule_approval)
        self.status_label.setText(_status_message_for_plan(plan))
        self._refresh_approval_state()

    def _display_target(self, target: RevisionTarget | None) -> None:
        if target is None:
            self.target_status_value.setText("none")
            self.target_regions_value.setText("none")
            self.target_scope_value.setText("none")
            return
        self.target_status_value.setText("ambiguous" if target.is_ambiguous else "resolved")
        self.target_regions_value.setText(", ".join(target.region_ids) or "none")
        self.target_scope_value.setText(target.target_scope.value)

    def _refresh_approval_state(self) -> None:
        plan = self._current_plan
        enabled = (
            plan is not None
            and not plan.target.is_ambiguous
            and plan.approval_status is not RevisionApprovalStatus.rejected
            and (
                not plan.requires_project_rule_approval
                or self.project_rule_confirmation.isChecked()
            )
        )
        self.approve_button.setEnabled(enabled)

    def _request_plan_approval(self) -> None:
        if self._current_plan is not None and self.approve_button.isEnabled():
            self.plan_approval_requested.emit(self._current_plan)


def _read_only_text(object_name: str) -> QPlainTextEdit:
    field = QPlainTextEdit()
    field.setObjectName(object_name)
    field.setReadOnly(True)
    field.setMaximumBlockCount(200)
    field.setFixedHeight(58)
    return field


def _format_proposals(plan: RevisionPlan) -> str:
    if not plan.proposals:
        return "none"
    return "\n".join(
        f"{proposal.action.value}: {proposal.before} -> {proposal.after}; "
        f"regions={', '.join(proposal.region_ids) or 'none'}"
        for proposal in plan.proposals
    )


def _format_state_issues(state: RevisionPreviewState) -> str:
    if not state.issue_summaries:
        return "none"
    return "\n".join(state.issue_summaries)


def _status_message_for_plan(plan: RevisionPlan) -> str:
    if plan.target.is_ambiguous:
        return plan.target.ambiguity_summary or "Revision target is ambiguous."
    if plan.requires_project_rule_approval:
        return "Project rule changes require separate confirmation."
    if plan.approval_status is RevisionApprovalStatus.approved:
        return "RevisionPlan is already approved; no edit has been applied by the UI."
    return "RevisionPlan preview ready; no edit has been applied."


def _status_message_for_state(state: RevisionPreviewState) -> str:
    if state.status == "target_ambiguous" and state.target is not None:
        return state.target.ambiguity_summary or "Revision target is ambiguous."
    if state.status == "rejected":
        return "Revision instruction was rejected."
    return f"Revision preview state: {state.status}"


__all__ = ["RevisionPlanPanel", "RevisionPreviewState"]
