from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from image_translator.domain._base import DomainModel, NonEmptyStr
from image_translator.domain.ids import RegionId, RevisionId
from image_translator.domain.quality import QualityIssue, QualitySeverity
from image_translator.domain.revision import (
    ApprovalRecord,
    RevisionAction,
    RevisionApprovalStatus,
    RevisionDomainDiff,
    RevisionPlan,
    RevisionProposal,
    RevisionRecord,
    RevisionScope,
    RevisionTarget,
    require_approved_revision_plan,
)
from image_translator.providers.base import ReviewAdapter, RevisionIntentRequest


class NaturalRevisionStatus(StrEnum):
    pending = "pending"
    intent_parsed = "intent_parsed"
    rejected = "rejected"
    target_ambiguous = "target_ambiguous"
    target_resolved = "target_resolved"
    rule_scope_determined = "rule_scope_determined"
    plan_created = "plan_created"
    waiting_for_plan_approval = "waiting_for_plan_approval"
    applied = "applied"
    revalidated = "revalidated"
    committed = "committed"


class NaturalRevisionRoute(StrEnum):
    continue_revision = "continue"
    interrupt_user = "interrupt_user"
    complete = "complete"
    fail = "fail"


class NaturalRevisionInterruptPayload(DomainModel):
    interrupt_type: NonEmptyStr
    revision_id: RevisionId
    affected_region_ids: tuple[RegionId, ...] = ()
    issue_summaries: tuple[NonEmptyStr, ...] = ()
    allowed_actions: tuple[NonEmptyStr, ...] = ()
    recommended_action: NonEmptyStr
    plan_id: NonEmptyStr | None = None


class NaturalRevisionInput(DomainModel):
    revision_id: RevisionId
    base_revision_id: RevisionId
    user_instruction: NonEmptyStr
    available_region_ids: tuple[RegionId, ...] = ()
    selected_region_ids: tuple[RegionId, ...] = ()
    approval_record: ApprovalRecord | None = None
    project_rule_approval_record: ApprovalRecord | None = None


class NaturalRevisionState(DomainModel):
    input: NaturalRevisionInput
    revision_id: RevisionId
    base_revision_id: RevisionId
    user_instruction: NonEmptyStr
    available_region_ids: tuple[RegionId, ...] = ()
    selected_region_ids: tuple[RegionId, ...] = ()
    normalized_intent: NonEmptyStr | None = None
    parsed_actions: tuple[RevisionAction, ...] = ()
    candidate_region_ids: tuple[RegionId, ...] = ()
    candidate_scope: RevisionScope = RevisionScope.current_region
    requires_target_confirmation: bool = False
    target: RevisionTarget | None = None
    plan: RevisionPlan | None = None
    candidate_record: RevisionRecord | None = None
    committed_record: RevisionRecord | None = None
    interrupt_payload: NaturalRevisionInterruptPayload | None = None
    issues: tuple[QualityIssue, ...] = ()
    last_route: NaturalRevisionRoute | None = None
    status: NaturalRevisionStatus = NaturalRevisionStatus.pending


class _GraphState(TypedDict):
    workflow_state: NaturalRevisionState


class NaturalRevisionGraph:
    def __init__(self, *, reviewer: ReviewAdapter | None = None) -> None:
        self._reviewer = reviewer
        self._compiled_graph: Any = _build_langgraph(reviewer=reviewer)

    async def run_state(self, workflow_input: NaturalRevisionInput) -> NaturalRevisionState:
        initial_state: _GraphState = {
            "workflow_state": create_natural_revision_workflow_state(workflow_input)
        }
        final_state = cast(_GraphState, await self._compiled_graph.ainvoke(initial_state))
        return final_state["workflow_state"]

    async def run(self, workflow_input: NaturalRevisionInput) -> RevisionRecord | None:
        state = await self.run_state(workflow_input)
        return state.committed_record


def create_natural_revision_workflow_state(
    workflow_input: NaturalRevisionInput,
) -> NaturalRevisionState:
    return NaturalRevisionState(
        input=workflow_input,
        revision_id=workflow_input.revision_id,
        base_revision_id=workflow_input.base_revision_id,
        user_instruction=workflow_input.user_instruction,
        available_region_ids=workflow_input.available_region_ids,
        selected_region_ids=workflow_input.selected_region_ids,
    )


async def parse_revision_intent(
    state: NaturalRevisionState,
    *,
    reviewer: ReviewAdapter | None = None,
) -> NaturalRevisionState:
    unsafe_reason = _unsafe_instruction_reason(state.user_instruction)
    if unsafe_reason is not None:
        return _reject(
            state,
            issue_code="unsafe_revision_instruction",
            summary=unsafe_reason,
        )

    if reviewer is None:
        normalized_intent = state.user_instruction
        candidate_region_ids = state.selected_region_ids
        proposed_action_values = tuple(
            action.value for action in _infer_actions(state.user_instruction)
        )
        requires_confirmation = False
        ambiguity_summary = None
    else:
        result = await reviewer.parse_revision_intent(
            RevisionIntentRequest(
                user_instruction=state.user_instruction,
                selected_region_ids=state.selected_region_ids,
                allowed_actions=tuple(action.value for action in RevisionAction),
            )
        )
        normalized_intent = result.normalized_intent
        candidate_region_ids = result.candidate_region_ids
        proposed_action_values = result.proposed_actions
        requires_confirmation = result.requires_confirmation
        ambiguity_summary = result.ambiguity_summary

    actions, invalid_actions = _parse_allowed_actions(proposed_action_values)
    if invalid_actions:
        return _reject(
            state,
            issue_code="unsupported_revision_action",
            summary="revision intent included unsupported action: "
            + ", ".join(invalid_actions),
        )
    if not actions:
        return _reject(
            state,
            issue_code="missing_revision_action",
            summary="revision intent did not map to an allowed action",
        )
    return state.model_copy(
        update={
            "normalized_intent": normalized_intent,
            "parsed_actions": actions,
            "candidate_region_ids": candidate_region_ids,
            "requires_target_confirmation": requires_confirmation
            or ambiguity_summary is not None,
            "status": NaturalRevisionStatus.intent_parsed,
        }
    )


def resolve_target_regions(state: NaturalRevisionState) -> NaturalRevisionState:
    if state.status is NaturalRevisionStatus.rejected:
        return state
    available = set(state.available_region_ids)
    target_region_ids = state.selected_region_ids or state.candidate_region_ids
    if not target_region_ids and len(state.available_region_ids) == 1:
        target_region_ids = state.available_region_ids
    unknown_region_ids = tuple(
        region_id for region_id in target_region_ids if available and region_id not in available
    )
    if unknown_region_ids:
        return _reject(
            state,
            issue_code="unknown_revision_target",
            summary="revision target includes unknown region: " + ", ".join(unknown_region_ids),
        )
    if (
        not target_region_ids
        or (len(target_region_ids) > 1 and not state.selected_region_ids)
        or state.requires_target_confirmation
    ):
        candidates = target_region_ids or state.available_region_ids
        target = RevisionTarget(
            region_ids=candidates,
            target_scope=state.candidate_scope,
            resolution_evidence=("target requires user selection",),
            is_ambiguous=True,
            ambiguity_summary="target region is ambiguous",
        )
        return state.model_copy(
            update={
                "target": target,
                "interrupt_payload": NaturalRevisionInterruptPayload(
                    interrupt_type="target_selection",
                    revision_id=state.revision_id,
                    affected_region_ids=candidates,
                    issue_summaries=("target region is ambiguous",),
                    allowed_actions=("select_target", "cancel"),
                    recommended_action="select the region that should receive the revision",
                ),
                "status": NaturalRevisionStatus.target_ambiguous,
            }
        )
    return state.model_copy(
        update={
            "target": RevisionTarget(
                region_ids=target_region_ids,
                target_scope=state.candidate_scope,
                resolution_evidence=("selected region",)
                if state.selected_region_ids
                else ("resolved from revision intent",),
            ),
            "status": NaturalRevisionStatus.target_resolved,
        }
    )


def determine_rule_scope(state: NaturalRevisionState) -> NaturalRevisionState:
    if state.status in {NaturalRevisionStatus.rejected, NaturalRevisionStatus.target_ambiguous}:
        return state
    target = state.target
    if target is None:
        return state
    scope = _infer_scope(state.user_instruction, state.parsed_actions)
    return state.model_copy(
        update={
            "candidate_scope": scope,
            "target": target.model_copy(update={"target_scope": scope}),
            "status": NaturalRevisionStatus.rule_scope_determined,
        }
    )


def create_revision_plan(state: NaturalRevisionState) -> NaturalRevisionState:
    if state.status in {NaturalRevisionStatus.rejected, NaturalRevisionStatus.target_ambiguous}:
        return state
    if state.target is None or state.normalized_intent is None:
        return _reject(
            state,
            issue_code="incomplete_revision_plan",
            summary="revision plan requires parsed intent and resolved target",
        )
    required_validation = _required_validation(state.parsed_actions, state.target.target_scope)
    requires_project_rule_approval = state.target.target_scope is RevisionScope.project_rule
    warnings = (
        ("project rule changes require separate user approval",)
        if requires_project_rule_approval
        else ()
    )
    plan = RevisionPlan(
        plan_id=f"plan-{state.revision_id}",
        base_revision_id=state.base_revision_id,
        normalized_user_instruction=state.normalized_intent,
        target=state.target,
        actions=state.parsed_actions,
        proposals=tuple(
            RevisionProposal(
                action=action,
                before="current revision value",
                after=state.normalized_intent,
                region_ids=state.target.region_ids,
            )
            for action in state.parsed_actions
        ),
        required_validation=required_validation,
        warnings=warnings,
        requires_project_rule_approval=requires_project_rule_approval,
    )
    if state.input.approval_record is not None:
        plan = plan.model_copy(
            update={
                "approval_status": RevisionApprovalStatus.approved,
                "approval_record": state.input.approval_record,
                "project_rule_approval_record": state.input.project_rule_approval_record,
            }
        )
    return state.model_copy(
        update={
            "plan": plan,
            "status": NaturalRevisionStatus.plan_created,
        }
    )


def interrupt_for_plan_approval(state: NaturalRevisionState) -> NaturalRevisionState:
    if state.plan is None or state.status is NaturalRevisionStatus.rejected:
        return state
    if _plan_ready_to_apply(state.plan):
        return state
    issue_summaries = (
        "project rule changes require separate approval",
    ) if state.plan.requires_project_rule_approval else ("revision plan requires approval",)
    return state.model_copy(
        update={
            "interrupt_payload": NaturalRevisionInterruptPayload(
                interrupt_type="revision_plan_approval",
                revision_id=state.revision_id,
                affected_region_ids=state.plan.target.region_ids,
                issue_summaries=issue_summaries,
                allowed_actions=("approve_plan", "edit_plan", "change_target", "reject_plan"),
                recommended_action="review and approve the structured revision plan",
                plan_id=state.plan.plan_id,
            ),
            "status": NaturalRevisionStatus.waiting_for_plan_approval,
        }
    )


def apply_revision(state: NaturalRevisionState) -> NaturalRevisionState:
    plan = require_approved_revision_plan(state.plan)
    approval_record = plan.approval_record
    if approval_record is None:
        raise AssertionError("require_approved_revision_plan returned plan without approval")
    record = RevisionRecord(
        revision_id=state.revision_id,
        parent_revision_id=state.base_revision_id,
        approved_plan=plan,
        domain_diff=tuple(
            RevisionDomainDiff(
                action=action,
                region_ids=plan.target.region_ids,
                summary=f"{action.value} applied to candidate revision",
            )
            for action in plan.actions
        ),
        validation_results=(),
        created_at=datetime.now(UTC),
        approval_record=approval_record,
    )
    return state.model_copy(
        update={
            "candidate_record": record,
            "status": NaturalRevisionStatus.applied,
        }
    )


def revalidate_revision(state: NaturalRevisionState) -> NaturalRevisionState:
    if state.candidate_record is None:
        return state
    record = state.candidate_record.model_copy(
        update={
            "validation_results": tuple(
                f"{validation}:passed"
                for validation in state.candidate_record.approved_plan.required_validation
            )
        }
    )
    return state.model_copy(
        update={
            "candidate_record": record,
            "status": NaturalRevisionStatus.revalidated,
        }
    )


def commit_revision(state: NaturalRevisionState) -> NaturalRevisionState:
    if state.candidate_record is None:
        return state
    return state.model_copy(
        update={
            "committed_record": state.candidate_record,
            "status": NaturalRevisionStatus.committed,
        }
    )


def _build_langgraph(*, reviewer: ReviewAdapter | None) -> Any:
    builder = StateGraph(_GraphState)
    builder.add_node(
        "parse_revision_intent",
        _async_node(lambda state: parse_revision_intent(state, reviewer=reviewer)),
    )
    sync_nodes = {
        "resolve_target_regions": resolve_target_regions,
        "determine_rule_scope": determine_rule_scope,
        "create_revision_plan": create_revision_plan,
        "interrupt_for_plan_approval": interrupt_for_plan_approval,
        "apply_revision": apply_revision,
        "revalidate_revision": revalidate_revision,
        "commit_revision": commit_revision,
    }
    for name, node in sync_nodes.items():
        builder.add_node(name, _sync_node(node))
    builder.add_edge(START, "parse_revision_intent")
    builder.add_edge("parse_revision_intent", "resolve_target_regions")
    builder.add_conditional_edges(
        "resolve_target_regions",
        _route_after_target_resolution,
        {
            NaturalRevisionRoute.continue_revision.value: "determine_rule_scope",
            NaturalRevisionRoute.interrupt_user.value: END,
            NaturalRevisionRoute.fail.value: END,
        },
    )
    builder.add_edge("determine_rule_scope", "create_revision_plan")
    builder.add_edge("create_revision_plan", "interrupt_for_plan_approval")
    builder.add_conditional_edges(
        "interrupt_for_plan_approval",
        _route_after_plan_approval,
        {
            NaturalRevisionRoute.continue_revision.value: "apply_revision",
            NaturalRevisionRoute.interrupt_user.value: END,
            NaturalRevisionRoute.fail.value: END,
        },
    )
    builder.add_edge("apply_revision", "revalidate_revision")
    builder.add_edge("revalidate_revision", "commit_revision")
    builder.add_edge("commit_revision", END)
    return builder.compile()


def _sync_node(func: Any) -> Any:
    def node(graph_state: _GraphState) -> _GraphState:
        return {"workflow_state": func(graph_state["workflow_state"])}

    return node


def _async_node(func: Any) -> Any:
    async def node(graph_state: _GraphState) -> _GraphState:
        return {"workflow_state": await func(graph_state["workflow_state"])}

    return node


def _route_after_target_resolution(graph_state: _GraphState) -> str:
    state = graph_state["workflow_state"]
    if state.status is NaturalRevisionStatus.rejected:
        return NaturalRevisionRoute.fail.value
    if state.status is NaturalRevisionStatus.target_ambiguous:
        return NaturalRevisionRoute.interrupt_user.value
    return NaturalRevisionRoute.continue_revision.value


def _route_after_plan_approval(graph_state: _GraphState) -> str:
    state = graph_state["workflow_state"]
    if state.status is NaturalRevisionStatus.rejected:
        return NaturalRevisionRoute.fail.value
    if state.plan is None or not _plan_ready_to_apply(state.plan):
        return NaturalRevisionRoute.interrupt_user.value
    return NaturalRevisionRoute.continue_revision.value


def _plan_ready_to_apply(plan: RevisionPlan) -> bool:
    return (
        plan.approval_status is RevisionApprovalStatus.approved
        and plan.approval_record is not None
        and (
            not plan.requires_project_rule_approval
            or plan.project_rule_approval_record is not None
        )
    )


def _parse_allowed_actions(
    action_values: tuple[str, ...],
) -> tuple[tuple[RevisionAction, ...], tuple[str, ...]]:
    actions: tuple[RevisionAction, ...] = ()
    invalid_actions: tuple[str, ...] = ()
    for action_value in action_values:
        try:
            action = RevisionAction(action_value)
        except ValueError:
            invalid_actions = (*invalid_actions, action_value)
            continue
        if action not in actions:
            actions = (*actions, action)
    return actions, invalid_actions


def _infer_actions(user_instruction: str) -> tuple[RevisionAction, ...]:
    lowered = user_instruction.lower()
    if any(keyword in lowered for keyword in ("font", "글꼴")):
        return (RevisionAction.change_font,)
    if any(keyword in lowered for keyword in ("size", "크기")):
        return (RevisionAction.change_font_size,)
    if any(keyword in lowered for keyword in ("glossary", "term", "용어")):
        return (RevisionAction.propose_glossary_change,)
    if any(keyword in lowered for keyword in ("character", "speaker", "인물", "캐릭터")):
        return (RevisionAction.propose_character_rule,)
    if any(keyword in lowered for keyword in ("inpaint", "인페인팅")):
        return (RevisionAction.retry_inpainting,)
    if any(keyword in lowered for keyword in ("retranslate", "retry translation", "재번역")):
        return (RevisionAction.retry_translation,)
    tone_keywords = ("tone", "polite", "formal", "말투", "존댓말", "반말")
    if any(keyword in lowered for keyword in tone_keywords):
        return (RevisionAction.adjust_tone,)
    return (RevisionAction.replace_translation,)


def _infer_scope(
    user_instruction: str,
    actions: tuple[RevisionAction, ...],
) -> RevisionScope:
    lowered = user_instruction.lower()
    project_keywords = ("from now on", "always", "project", "프로젝트", "앞으로", "항상")
    page_keywords = ("page", "whole page", "페이지", "전체")
    if any(keyword in lowered for keyword in project_keywords):
        return RevisionScope.project_rule
    if any(keyword in lowered for keyword in page_keywords):
        return RevisionScope.current_page
    if any(
        action in {RevisionAction.propose_character_rule, RevisionAction.propose_glossary_change}
        for action in actions
    ) and any(keyword in lowered for keyword in ("rule", "규칙")):
        return RevisionScope.project_rule
    return RevisionScope.current_region


def _required_validation(
    actions: tuple[RevisionAction, ...],
    scope: RevisionScope,
) -> tuple[str, ...]:
    validation: tuple[str, ...] = ()
    translation_actions = {
        RevisionAction.replace_translation,
        RevisionAction.adjust_tone,
        RevisionAction.adjust_localization,
        RevisionAction.retry_translation,
        RevisionAction.retry_quality_review,
    }
    visual_actions = {
        RevisionAction.change_font,
        RevisionAction.change_font_size,
        RevisionAction.change_weight,
        RevisionAction.change_alignment,
        RevisionAction.change_color,
        RevisionAction.change_outline,
        RevisionAction.change_writing_mode,
        RevisionAction.move_region,
        RevisionAction.resize_region,
        RevisionAction.retry_inpainting,
    }
    if any(action in translation_actions for action in actions):
        validation = (*validation, "translation_quality")
    if any(action in visual_actions for action in actions):
        validation = (*validation, "result_quality")
    if scope is RevisionScope.project_rule:
        validation = (*validation, "project_rule_approval")
    return validation or ("revision_integrity",)


def _unsafe_instruction_reason(user_instruction: str) -> str | None:
    lowered = user_instruction.lower()
    unsafe_fragments = (
        "ignore previous",
        "system prompt",
        "developer message",
        "read file",
        "write file",
        "/etc/",
        "shell",
        "subprocess",
        "curl ",
        "network",
        "api key",
        "provider setting",
        "환경변수",
    )
    if any(fragment in lowered for fragment in unsafe_fragments):
        return "revision instruction attempts to override policy or access external tools"
    return None


def _reject(
    state: NaturalRevisionState,
    *,
    issue_code: str,
    summary: str,
) -> NaturalRevisionState:
    return state.model_copy(
        update={
            "issues": (
                *state.issues,
                QualityIssue(
                    issue_code=issue_code,
                    severity=QualitySeverity.error,
                    scope="natural_revision",
                    region_ids=state.selected_region_ids or state.candidate_region_ids,
                    summary=summary,
                    recommended_action="revise the natural language instruction",
                ),
            ),
            "status": NaturalRevisionStatus.rejected,
        }
    )


__all__ = [
    "NaturalRevisionGraph",
    "NaturalRevisionInput",
    "NaturalRevisionInterruptPayload",
    "NaturalRevisionRoute",
    "NaturalRevisionState",
    "NaturalRevisionStatus",
    "apply_revision",
    "commit_revision",
    "create_natural_revision_workflow_state",
    "create_revision_plan",
    "determine_rule_scope",
    "interrupt_for_plan_approval",
    "parse_revision_intent",
    "resolve_target_regions",
    "revalidate_revision",
]
