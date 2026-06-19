from __future__ import annotations

from image_translator.domain.ids import RevisionId
from image_translator.domain.job import JobDefinition
from image_translator.workflows.mock_core import (
    MOCK_REVISION_ID,
    MockCoreOCRAdapter,
    MockCoreReviewAdapter,
    MockCoreTranslatorAdapter,
    ProviderBackedMockCoreWorkflow,
    RunImageTranslationResult,
)


class RunImageTranslationUseCase:
    def __init__(
        self,
        *,
        ocr_adapter: MockCoreOCRAdapter,
        translator_adapter: MockCoreTranslatorAdapter,
        review_adapter: MockCoreReviewAdapter,
        revision_id: RevisionId = MOCK_REVISION_ID,
    ) -> None:
        self._workflow = ProviderBackedMockCoreWorkflow(
            ocr_adapter=ocr_adapter,
            translator_adapter=translator_adapter,
            review_adapter=review_adapter,
            revision_id=revision_id,
        )

    async def run(self, job: JobDefinition) -> RunImageTranslationResult:
        return await self._workflow.run(job)


__all__ = [
    "MOCK_REVISION_ID",
    "RunImageTranslationResult",
    "RunImageTranslationUseCase",
]
