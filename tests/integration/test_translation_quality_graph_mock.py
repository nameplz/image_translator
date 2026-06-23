from __future__ import annotations

import pytest

from image_translator.domain.geometry import Point, Polygon
from image_translator.domain.ocr import (
    NormalizedTextRegion,
    ReadingOrder,
    TextOrientation,
    TextRole,
    WritingMode,
)
from image_translator.providers import MockReviewAdapter, MockTranslatorAdapter
from image_translator.workflows.translation_quality import (
    TranslationQualityGraph,
    TranslationWorkflowInput,
)


@pytest.mark.asyncio
async def test_mock_graph_omits_visual_references_when_visual_mode_is_off() -> None:
    translator = MockTranslatorAdapter()
    reviewer = MockReviewAdapter()
    graph = TranslationQualityGraph(translator=translator, reviewer=reviewer)

    result = await graph.run(
        TranslationWorkflowInput(
            job_id="job-translation-quality-mock",
            project_id="project-1",
            revision_id="revision-1",
            source_image_reference="source-page-1",
            source_language="ja",
            target_language="ko",
            regions=(_region("region-1", 0), _region("region-2", 1)),
            primary_ocr_snapshots=(),
            translator_provider_id=translator.provider_id,
            reviewer_provider_id=reviewer.provider_id,
            visual_mode=False,
            image_transmission_consent=False,
        )
    )

    assert tuple(
        translation.region_id for translation in result.approved_translation_results
    ) == ("region-1", "region-2")
    assert result.unresolved_issues == ()
    assert all(record.visual_references == () for record in translator.recorded_requests)
    assert all(record.visual_references == () for record in reviewer.recorded_requests)


def _region(region_id: str, item_index: int) -> NormalizedTextRegion:
    return NormalizedTextRegion(
        region_id=region_id,
        source_text=f"source text {item_index}",
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
