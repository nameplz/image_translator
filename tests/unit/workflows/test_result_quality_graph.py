from __future__ import annotations

from datetime import UTC, datetime

import pytest

from image_translator.domain.export import (
    VISUAL_QUALITY_UNCONFIRMED,
    ExportMode,
    ForceApprovalRecord,
)
from image_translator.domain.geometry import Point, Polygon
from image_translator.domain.ocr import WritingMode
from image_translator.domain.quality import ApprovalStatus
from image_translator.domain.render import RenderedRegion, RenderPlan, RenderStyle, RGBColor
from image_translator.domain.translation import TranslationResult
from image_translator.services.export_gate import evaluate_export_eligibility
from image_translator.workflows.result_quality import (
    ResultCorrectionAction,
    ResultQualityGraph,
    ResultQualityInput,
    create_result_quality_workflow_state,
    finalize_result,
    inspect_layout,
    plan_result_corrections,
    route_result_decision,
)


def test_inspect_layout_reports_clipping_overlap_and_glyph_issues() -> None:
    state = inspect_layout(
        create_result_quality_workflow_state(
            _workflow_input(
                rendered_regions=(
                    _rendered_region(
                        "region-1",
                        output_geometry=_polygon(80, 10, 130, 40),
                        text="bad\ufffd",
                    ),
                    _rendered_region("region-2", output_geometry=_polygon(90, 20, 120, 50)),
                )
            )
        )
    )

    assert {issue.issue_code for issue in state.unresolved_issues} == {
        "text_clipping",
        "text_overlap",
        "unsupported_glyph",
    }


def test_plan_result_corrections_uses_only_allowed_actions() -> None:
    state = plan_result_corrections(
        inspect_layout(
            create_result_quality_workflow_state(
                _workflow_input(
                    rendered_regions=(
                        _rendered_region(
                            "region-1",
                            output_geometry=_polygon(80, 10, 130, 40),
                            text="bad\ufffd",
                        ),
                    )
                )
            )
        )
    )

    assert state.correction_plan
    assert {correction.action for correction in state.correction_plan} <= {
        ResultCorrectionAction.render_plan_update,
        ResultCorrectionAction.mask_update,
        ResultCorrectionAction.backend_escalation,
        ResultCorrectionAction.rerender,
    }


def test_visual_mode_off_final_result_keeps_confirmation_and_blocks_export() -> None:
    state = finalize_result(
        create_result_quality_workflow_state(_workflow_input(visual_mode=False))
    )

    assert state.final_image_result is not None
    assert state.final_image_result.approval_status is ApprovalStatus.needs_review
    assert state.final_image_result.visual_quality_checked is False
    assert state.final_image_result.requires_user_confirmation == (
        VISUAL_QUALITY_UNCONFIRMED,
    )

    decision = evaluate_export_eligibility(state.final_image_result)
    assert decision.allowed is False
    assert "user_confirmation_required" in decision.reason_codes


def test_required_user_confirmation_blocks_until_force_record_covers_it() -> None:
    state = finalize_result(
        create_result_quality_workflow_state(_workflow_input(visual_mode=False))
    )
    assert state.final_image_result is not None

    missing_record_decision = evaluate_export_eligibility(state.final_image_result)
    assert missing_record_decision.allowed is False

    force_record = ForceApprovalRecord(
        affected_revision=state.final_image_result.revision_id,
        reason="User reviewed the final preview and accepts visual uncertainty.",
        created_at=datetime(2026, 6, 24, 12, 0, tzinfo=UTC),
        requires_user_confirmation=(VISUAL_QUALITY_UNCONFIRMED,),
    )
    forced_state = finalize_result(
        create_result_quality_workflow_state(_workflow_input(visual_mode=False)),
        force_approval_record=force_record,
    )
    assert forced_state.export_decision is not None
    forced_decision = forced_state.export_decision

    assert forced_decision.allowed is True
    assert forced_decision.mode is ExportMode.forced
    assert forced_decision.force_approval_record == force_record


@pytest.mark.asyncio
async def test_graph_stops_after_two_automatic_correction_attempts() -> None:
    graph = ResultQualityGraph()

    state = await graph.run_state(
        _workflow_input(
            rendered_regions=(
                _rendered_region("region-1", output_geometry=_polygon(80, 10, 130, 40)),
            ),
            visual_mode=True,
            image_transmission_consent=True,
        )
    )

    assert state.correction_attempts == 2
    assert route_result_decision(state).value == "interrupt_user"
    assert state.interrupt_payload is not None
    assert state.interrupt_payload.affected_region_ids == ("region-1",)


def _workflow_input(
    *,
    rendered_regions: tuple[RenderedRegion, ...] | None = None,
    visual_mode: bool = True,
    image_transmission_consent: bool = True,
) -> ResultQualityInput:
    return ResultQualityInput(
        revision_id="revision-result-quality",
        approved_translations=(_translation("region-1"),),
        source_image_reference="source-page",
        inpainted_image_reference="inpainted-page",
        rendered_image_reference="rendered-page",
        expected_region_ids=("region-1",),
        render_plans=(_plan("region-1"),),
        rendered_regions=rendered_regions or (_rendered_region("region-1"),),
        image_size=(100, 100),
        visual_mode=visual_mode,
        image_transmission_consent=image_transmission_consent,
    )


def _translation(region_id: str) -> TranslationResult:
    return TranslationResult(
        region_id=region_id,
        approved_translated_text="translated text",
        source_language="ja",
        target_language="ko",
        selected_candidate_id=f"candidate-{region_id}",
        approval_status=ApprovalStatus.approved_automatic.value,
    )


def _rendered_region(
    region_id: str,
    *,
    output_geometry: Polygon | None = None,
    text: str = "translated text",
) -> RenderedRegion:
    plan = _plan(region_id, text=text)
    return RenderedRegion(
        region_id=region_id,
        applied_plan=plan,
        output_geometry=output_geometry or plan.geometry,
    )


def _plan(region_id: str, *, text: str = "translated text") -> RenderPlan:
    return RenderPlan(
        region_id=region_id,
        geometry=_polygon(10, 10, 50, 30),
        translated_text=text,
        style=RenderStyle(
            size=14,
            color=RGBColor(red=0, green=0, blue=0),
            writing_mode=WritingMode.horizontal_ltr,
        ),
    )


def _polygon(left: float, top: float, right: float, bottom: float) -> Polygon:
    return Polygon(
        points=(
            Point(x=left, y=top),
            Point(x=right, y=top),
            Point(x=right, y=bottom),
            Point(x=left, y=bottom),
        )
    )
