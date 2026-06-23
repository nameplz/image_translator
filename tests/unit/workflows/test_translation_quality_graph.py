from __future__ import annotations

from collections.abc import Mapping

import pytest

from image_translator.domain.errors import TranslationResultMismatchError
from image_translator.domain.geometry import Point, Polygon
from image_translator.domain.ocr import (
    NormalizedTextRegion,
    ReadingOrder,
    TextOrientation,
    TextRole,
    WritingMode,
)
from image_translator.domain.quality import (
    QualityIssue,
    QualitySeverity,
    RegionReview,
    RubricScores,
)
from image_translator.domain.translation import TranslationCandidate, TranslationRequest
from image_translator.providers.base import (
    LanguagePair,
    OCRCorrectionRequest,
    OCRCorrectionReview,
    PageContextRequest,
    PageContextReview,
    PageReview,
    ProviderCapabilities,
    ProviderConfigIssue,
    ProviderType,
    ResultImageReviewRequest,
    ResultQualityReview,
    RevisionIntentParseResult,
    RevisionIntentRequest,
    TranslationReviewRequest,
)
from image_translator.workflows.translation_quality import (
    TranslationQualityGraph,
    TranslationWorkflowInput,
)


class ScriptedTranslator:
    provider_id = "scripted-translator"
    display_name = "Scripted Translator"

    def __init__(
        self,
        scripts: tuple[tuple[TranslationCandidate, ...] | None, ...] = (),
    ) -> None:
        self._scripts = scripts
        self.calls: tuple[tuple[str, ...], ...] = ()

    async def load(self) -> None:
        return None

    async def unload(self) -> None:
        return None

    def validate_config(self) -> tuple[ProviderConfigIssue, ...]:
        return ()

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_type=ProviderType.translator,
            supported_language_pairs=(LanguagePair(source_language="ja", target_language="ko"),),
            supports_batch=True,
            max_batch_size=16,
            supports_structured_output=True,
            is_cloud=False,
        )

    async def translate_page(
        self,
        requests: tuple[TranslationRequest, ...],
    ) -> tuple[TranslationCandidate, ...]:
        call_number = len(self.calls) + 1
        self.calls = (*self.calls, tuple(request.region_id for request in requests))
        scripted = self._scripts[call_number - 1] if call_number <= len(self._scripts) else None
        if scripted is not None:
            return scripted
        return tuple(
            _candidate(
                region_id=request.region_id,
                text=f"{request.region_id}-translation-call-{call_number}",
                suffix=str(call_number),
            )
            for request in requests
        )


class ScriptedReviewer:
    provider_id = "scripted-reviewer"
    display_name = "Scripted Reviewer"

    def __init__(self, scripts: tuple[Mapping[str, RegionReview], ...]) -> None:
        self._scripts = scripts
        self.translation_review_calls: tuple[tuple[str, ...], ...] = ()

    async def load(self) -> None:
        return None

    async def unload(self) -> None:
        return None

    def validate_config(self) -> tuple[ProviderConfigIssue, ...]:
        return ()

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_type=ProviderType.reviewer,
            supported_language_pairs=(LanguagePair(source_language="ja", target_language="ko"),),
            supports_batch=True,
            max_batch_size=16,
            supports_structured_output=True,
            is_cloud=False,
        )

    async def correct_ocr(
        self,
        request: OCRCorrectionRequest,
    ) -> OCRCorrectionReview:
        candidate = request.candidates[0] if request.candidates else None
        return OCRCorrectionReview(
            region_id=candidate.region_id if candidate is not None else None,
            selected_candidate_id=candidate.request_id if candidate is not None else None,
            corrected_text=candidate.text if candidate is not None else None,
            confidence=candidate.confidence if candidate is not None else 0.0,
            evidence_summary="scripted OCR correction",
        )

    async def build_page_context(
        self,
        request: PageContextRequest,
    ) -> PageContextReview:
        return PageContextReview(
            scene_summary="scripted page context",
            reading_order_notes="scripted reading order",
            confidence=0.9,
        )

    async def review_translation(
        self,
        request: TranslationReviewRequest,
    ) -> PageReview:
        self.translation_review_calls = (
            *self.translation_review_calls,
            tuple(candidate.region_id for candidate in request.candidates),
        )
        script_index = min(len(self.translation_review_calls) - 1, len(self._scripts) - 1)
        script = self._scripts[script_index]
        return PageReview(
            region_reviews=tuple(script[region_id] for region_id in request.region_ids),
            context_consistency_summary="scripted translation review",
            provider_id=self.provider_id,
            model_id="scripted-reviewer-v1",
            prompt_contract_version=request.prompt_contract_version,
        )

    async def review_result_image(
        self,
        request: ResultImageReviewRequest,
    ) -> ResultQualityReview:
        return ResultQualityReview(
            rendered_image_reference=request.rendered_image_reference,
            decision="approve",
        )

    async def parse_revision_intent(
        self,
        request: RevisionIntentRequest,
    ) -> RevisionIntentParseResult:
        return RevisionIntentParseResult(
            normalized_intent=request.user_instruction,
            candidate_region_ids=request.selected_region_ids,
            proposed_actions=request.allowed_actions,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "message"),
    (
        ("missing", "cardinality"),
        ("duplicate", "duplicate"),
        ("unknown", "mismatch"),
    ),
)
async def test_candidate_region_id_errors_happen_before_translation_review(
    case_name: str,
    message: str,
) -> None:
    bad_candidates = _bad_candidates(case_name)
    translator = ScriptedTranslator(scripts=(bad_candidates,))
    reviewer = ScriptedReviewer(
        scripts=(
            {
                "region-1": _approved_review("region-1"),
                "region-2": _approved_review("region-2"),
            },
        )
    )
    graph = TranslationQualityGraph(translator=translator, reviewer=reviewer)

    with pytest.raises(TranslationResultMismatchError, match=message):
        await graph.run(_workflow_input())

    assert reviewer.translation_review_calls == ()


@pytest.mark.asyncio
async def test_retry_retranslates_only_failed_regions_and_keeps_approved_text() -> None:
    translator = ScriptedTranslator()
    reviewer = ScriptedReviewer(
        scripts=(
            {
                "region-1": _approved_review("region-1"),
                "region-2": _retryable_review("region-2"),
            },
            {"region-2": _approved_review("region-2")},
        )
    )
    graph = TranslationQualityGraph(translator=translator, reviewer=reviewer)

    result = await graph.run(_workflow_input())

    approved_by_region = {
        translation.region_id: translation.approved_translated_text
        for translation in result.approved_translation_results
    }
    assert approved_by_region == {
        "region-1": "region-1-translation-call-1",
        "region-2": "region-2-translation-call-2",
    }
    assert translator.calls == (("region-1", "region-2"), ("region-2",))
    assert reviewer.translation_review_calls == (("region-1", "region-2"), ("region-2",))
    assert result.interrupt_payload is None


@pytest.mark.asyncio
async def test_max_two_translation_attempts_interrupts_only_problem_regions() -> None:
    translator = ScriptedTranslator()
    reviewer = ScriptedReviewer(
        scripts=(
            {
                "region-1": _approved_review("region-1"),
                "region-2": _retryable_review("region-2"),
            },
            {"region-2": _retryable_review("region-2")},
        )
    )
    graph = TranslationQualityGraph(translator=translator, reviewer=reviewer)

    result = await graph.run(_workflow_input())

    assert translator.calls == (("region-1", "region-2"), ("region-2",))
    assert tuple(
        translation.region_id for translation in result.approved_translation_results
    ) == ("region-1",)
    assert result.interrupt_payload is not None
    assert result.interrupt_payload.affected_region_ids == ("region-2",)
    assert tuple(issue.region_ids for issue in result.unresolved_issues) == (("region-2",),)


def _workflow_input() -> TranslationWorkflowInput:
    return TranslationWorkflowInput(
        job_id="job-translation-quality",
        project_id="project-1",
        revision_id="revision-1",
        source_image_reference="source-page-1",
        source_language="ja",
        target_language="ko",
        regions=(_region("region-1", "source 1", 0), _region("region-2", "source 2", 1)),
        primary_ocr_snapshots=(),
        translator_provider_id="scripted-translator",
        reviewer_provider_id="scripted-reviewer",
        visual_mode=False,
        image_transmission_consent=False,
    )


def _region(region_id: str, source_text: str, item_index: int) -> NormalizedTextRegion:
    return NormalizedTextRegion(
        region_id=region_id,
        source_text=source_text,
        geometry=Polygon(
            points=(
                Point(x=float(item_index * 20), y=0.0),
                Point(x=float(item_index * 20 + 10), y=0.0),
                Point(x=float(item_index * 20), y=10.0),
            )
        ),
        source_language="ja",
        writing_mode=WritingMode.horizontal_ltr,
        orientation=TextOrientation.upright,
        reading_order=ReadingOrder(
            page_index=0,
            group_index=0,
            item_index=item_index,
            confidence=0.95,
        ),
        text_role=TextRole.dialogue,
    )


def _candidate(region_id: str, text: str, suffix: str) -> TranslationCandidate:
    return TranslationCandidate(
        candidate_id=f"candidate-{suffix}-{region_id}",
        region_id=region_id,
        translated_text=text,
        provider_id="scripted-translator",
        model_id="scripted-translator-v1",
        attempt=1,
        request_fingerprint=f"fingerprint-{suffix}-{region_id}",
        created_revision="revision-1",
    )


def _bad_candidates(case_name: str) -> tuple[TranslationCandidate, ...]:
    if case_name == "missing":
        return (_candidate(region_id="region-1", text="translated 1", suffix="missing"),)
    if case_name == "duplicate":
        return (
            _candidate(region_id="region-1", text="translated 1", suffix="dup-a"),
            _candidate(region_id="region-1", text="translated 1 again", suffix="dup-b"),
        )
    return (
        _candidate(region_id="region-1", text="translated 1", suffix="unknown-a"),
        _candidate(region_id="unknown-region", text="unexpected", suffix="unknown-b"),
    )


def _approved_review(region_id: str) -> RegionReview:
    return RegionReview(
        region_id=region_id,
        rubric_scores=_scores(),
        total_score=4.5,
        evidence_summary="translation preserves meaning and voice",
        improvement_instruction=None,
        decision="approve",
    )


def _retryable_review(region_id: str) -> RegionReview:
    return RegionReview(
        region_id=region_id,
        rubric_scores=_scores(semantic_fidelity=3.0),
        total_score=3.5,
        critical_issues=(),
        non_critical_issues=(
            QualityIssue(
                issue_code=f"semantic_low_{region_id}",
                severity=QualitySeverity.warning,
                scope="translation",
                region_ids=(region_id,),
                summary="meaning is too loose",
                evidence_references=("review",),
                recommended_action="preserve the exact source meaning",
            ),
        ),
        evidence_summary="semantic fidelity is below threshold",
        improvement_instruction="preserve the exact source meaning",
        decision="retry_quality",
    )


def _scores(
    *,
    semantic_fidelity: float = 4.5,
    completeness: float = 4.5,
    naturalness: float = 4.5,
    character_voice: float = 4.5,
    context_fit: float = 4.5,
    terminology: float = 4.5,
    text_role_fit: float = 4.5,
    renderability: float = 4.5,
) -> RubricScores:
    return RubricScores(
        semantic_fidelity=semantic_fidelity,
        completeness=completeness,
        naturalness=naturalness,
        character_voice=character_voice,
        context_fit=context_fit,
        terminology=terminology,
        text_role_fit=text_role_fit,
        renderability=renderability,
    )
