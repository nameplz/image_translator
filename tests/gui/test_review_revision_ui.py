from __future__ import annotations

from typing import Any

from image_translator.domain import (
    NormalizedTextRegion,
    Point,
    Polygon,
    QualityIssue,
    QualitySeverity,
    ReadingOrder,
    RegionReview,
    RenderPlan,
    RenderStyle,
    RevisionAction,
    RevisionPlan,
    RevisionProposal,
    RevisionScope,
    RevisionTarget,
    RubricScores,
    TextOrientation,
    TextRole,
    TranslationCandidate,
    TranslationResult,
    WritingMode,
)
from image_translator.domain.quality import ApprovalStatus
from image_translator.gui.main_window import MainWindow
from image_translator.gui.review_panel import ReviewRegionState
from image_translator.gui.revision_panel import RevisionPlanPanel, RevisionPreviewState
from image_translator.gui.viewer import ImageOverlayViewer


def test_review_queue_filters_out_approved_items(qtbot: Any) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    window.set_review_regions(
        (
            _review_state("region-approved", ApprovalStatus.approved_automatic),
            _review_state("region-waiting", ApprovalStatus.needs_review),
            _review_state("region-rejected", ApprovalStatus.rejected),
        )
    )

    assert window.review_queue.visible_region_ids() == ("region-waiting", "region-rejected")


def test_selected_region_updates_overlay_and_inspector(qtbot: Any) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    state = _review_state("region-2", ApprovalStatus.needs_review)

    window.set_review_regions((state,))
    window.select_region("region-2")

    assert window.overlay_viewer.selected_region_id == "region-2"
    assert window.region_inspector.region_id_value.text() == "region-2"
    assert window.region_inspector.writing_mode_value.text() == "vertical_rl"
    assert window.region_inspector.text_role_value.text() == "dialogue"
    assert "meaning changed" in window.region_inspector.issues_value.toPlainText()


def test_overlay_viewer_exposes_deterministic_region_state(qtbot: Any) -> None:
    viewer = ImageOverlayViewer()
    qtbot.addWidget(viewer)
    state = _review_state("region-1", ApprovalStatus.needs_review)

    viewer.set_regions((state.region,), state.issues)
    viewer.select_region("region-1")

    assert viewer.region_rows() == (
        "region-1 | polygon=(0,0) (100,0) (100,60) (0,60) | "
        "mode=vertical_rl | order=0.1.2 | role=dialogue | severity=critical | selected=yes",
    )


def test_revision_plan_preview_blocks_ambiguous_target(qtbot: Any) -> None:
    panel = RevisionPlanPanel()
    qtbot.addWidget(panel)
    plan = _revision_plan(is_ambiguous=True)

    panel.display_plan(request_id=1, plan=plan)

    assert panel.approve_button.isEnabled() is False
    assert panel.target_status_value.text() == "ambiguous"
    assert "select a specific target" in panel.status_label.text()


def test_revision_plan_preview_requires_project_rule_confirmation(qtbot: Any) -> None:
    panel = RevisionPlanPanel()
    qtbot.addWidget(panel)
    plan = _revision_plan(scope=RevisionScope.project_rule, requires_project_rule_approval=True)

    panel.display_plan(request_id=1, plan=plan)

    assert panel.project_rule_confirmation.isEnabled() is True
    assert panel.project_rule_confirmation.isChecked() is False
    assert panel.approve_button.isEnabled() is False

    panel.project_rule_confirmation.setChecked(True)

    assert panel.approve_button.isEnabled() is True


def test_revision_panel_discards_stale_plan_preview(qtbot: Any) -> None:
    panel = RevisionPlanPanel()
    qtbot.addWidget(panel)

    first_request = panel.begin_preview("make this more polite")
    second_request = panel.begin_preview("make this shorter")

    panel.display_plan(request_id=first_request, plan=_revision_plan(plan_id="plan-old"))
    assert panel.plan_id_value.text() == "pending"

    panel.display_plan(request_id=second_request, plan=_revision_plan(plan_id="plan-new"))

    assert panel.plan_id_value.text() == "plan-new"
    assert panel.normalized_instruction_value.toPlainText() == "make this more polite"


def test_revision_panel_displays_natural_revision_state(qtbot: Any) -> None:
    panel = RevisionPlanPanel()
    qtbot.addWidget(panel)
    state = RevisionPreviewState(
        status="target_ambiguous",
        normalized_instruction="make this more polite",
        target=RevisionTarget(
            region_ids=("region-1", "region-2"),
            is_ambiguous=True,
            ambiguity_summary="target region is ambiguous",
        ),
    )

    panel.display_preview_state(request_id=1, state=state)

    assert panel.approve_button.isEnabled() is False
    assert panel.target_status_value.text() == "ambiguous"
    assert panel.target_regions_value.text() == "region-1, region-2"


def _review_state(region_id: str, approval_status: ApprovalStatus) -> ReviewRegionState:
    region = NormalizedTextRegion(
        region_id=region_id,
        source_text="原文",
        geometry=_polygon(),
        source_language="ja",
        writing_mode=WritingMode.vertical_rl,
        orientation=TextOrientation.upright,
        reading_order=ReadingOrder(
            page_index=0,
            group_index=1,
            item_index=2,
            confidence=0.88,
        ),
        text_role=TextRole.dialogue,
    )
    issue = QualityIssue(
        issue_code="meaning_changed",
        severity=QualitySeverity.critical,
        scope="translation",
        region_ids=(region_id,),
        summary="meaning changed",
        recommended_action="revise translation",
    )
    candidate = TranslationCandidate(
        candidate_id=f"candidate-{region_id}",
        region_id=region_id,
        translated_text="translated text",
        provider_id="mock-translator",
        model_id="mock-model",
        attempt=1,
        request_fingerprint=f"request-{region_id}",
        created_revision="revision-base",
    )
    result = TranslationResult(
        region_id=region_id,
        approved_translated_text="approved text",
        source_language="ja",
        target_language="ko",
        selected_candidate_id=f"candidate-{region_id}",
        approval_status=approval_status.value,
        review_reference="review-1",
    )
    return ReviewRegionState(
        region=region,
        primary_ocr_text="primary text",
        secondary_ocr_text="secondary text",
        approved_ocr_text="approved text",
        translation_candidates=(candidate,),
        approved_translation=result,
        review=_review(region_id, issue),
        issues=(issue,),
        render_plan=RenderPlan(
            region_id=region_id,
            geometry=region.geometry,
            translated_text="approved text",
            style=RenderStyle(size=20, writing_mode=WritingMode.horizontal_ltr),
            source_style_evidence=("matched source bubble",),
        ),
        approval_status=approval_status,
    )


def _review(region_id: str, issue: QualityIssue) -> RegionReview:
    return RegionReview(
        region_id=region_id,
        rubric_scores=RubricScores(
            semantic_fidelity=2.0,
            completeness=4.0,
            naturalness=4.0,
            character_voice=3.0,
            context_fit=3.0,
            terminology=4.0,
            text_role_fit=4.0,
            renderability=4.0,
        ),
        total_score=3.4,
        critical_issues=(issue,),
        evidence_summary="review evidence",
        improvement_instruction="preserve the original meaning",
        decision="needs_review",
    )


def _revision_plan(
    *,
    plan_id: str = "plan-1",
    is_ambiguous: bool = False,
    scope: RevisionScope = RevisionScope.current_region,
    requires_project_rule_approval: bool = False,
) -> RevisionPlan:
    target = RevisionTarget(
        region_ids=("region-1", "region-2") if is_ambiguous else ("region-1",),
        target_scope=scope,
        resolution_evidence=("selected region",),
        is_ambiguous=is_ambiguous,
        ambiguity_summary="select a specific target" if is_ambiguous else None,
    )
    return RevisionPlan(
        plan_id=plan_id,
        base_revision_id="revision-base",
        normalized_user_instruction="make this more polite",
        target=target,
        actions=(RevisionAction.adjust_tone,),
        proposals=(
            RevisionProposal(
                action=RevisionAction.adjust_tone,
                before="current revision value",
                after="make this more polite",
                region_ids=target.region_ids,
            ),
        ),
        required_validation=("translation_quality",),
        warnings=("project rule changes require separate user approval",)
        if requires_project_rule_approval
        else (),
        requires_project_rule_approval=requires_project_rule_approval,
    )


def _polygon() -> Polygon:
    return Polygon(
        points=(
            Point(x=0.0, y=0.0),
            Point(x=100.0, y=0.0),
            Point(x=100.0, y=60.0),
            Point(x=0.0, y=60.0),
        )
    )
