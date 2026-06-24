from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from image_translator.domain import JobDefinition, JobStatus, WorkflowCancelled
from image_translator.persistence.checkpoints import SQLiteCheckpointStore, WorkflowGraphKind
from image_translator.providers import MockOCRAdapter, MockReviewAdapter, MockTranslatorAdapter
from image_translator.use_cases.resume_job import ResumeJobUseCase
from image_translator.use_cases.run_image_translation import RunImageTranslationUseCase


def _job() -> JobDefinition:
    return JobDefinition(
        job_id="job-resume-1",
        project_id="project-1",
        input_path="/safe/local/input.png",
        requested_output_path="/safe/local/output.png",
        source_language="ja",
        target_language="ko",
        provider_selection=("mock-ocr", "mock-translator", "mock-reviewer"),
    )


@pytest.mark.asyncio
async def test_resume_mock_workflow_skips_completed_provider_calls(tmp_path: Path) -> None:
    store = SQLiteCheckpointStore(database_path=tmp_path / "checkpoints.sqlite3")
    translator = MockTranslatorAdapter()
    use_case = ResumeJobUseCase(
        checkpoint_store=store,
        workflow=RunImageTranslationUseCase(
            ocr_adapter=MockOCRAdapter(),
            translator_adapter=translator,
            review_adapter=MockReviewAdapter(),
        ),
        graph_kind=WorkflowGraphKind.translation_quality,
        revision_id="mock-revision-1",
    )

    first = await use_case.resume(_job())
    second = await use_case.resume(_job())

    assert first.resumed_from_checkpoint is False
    assert second.resumed_from_checkpoint is True
    assert len(translator.recorded_requests) == 1
    assert second.snapshot.status is first.snapshot.status
    assert store.has_completed_provider_call(
        thread_id=use_case.thread_id_for(_job()),
        request_fingerprint=translator.recorded_requests[0].request_fingerprint,
    )


@pytest.mark.asyncio
async def test_resume_serializes_cancelled_status(tmp_path: Path) -> None:
    class _CancellingWorkflow:
        async def run(self, job: JobDefinition) -> object:
            raise asyncio.CancelledError

    store = SQLiteCheckpointStore(database_path=tmp_path / "checkpoints.sqlite3")
    use_case = ResumeJobUseCase(
        checkpoint_store=store,
        workflow=_CancellingWorkflow(),
        graph_kind=WorkflowGraphKind.translation_quality,
        revision_id="mock-revision-1",
    )

    result = await use_case.resume(_job())

    assert result.snapshot.status is JobStatus.cancelled
    assert result.snapshot.can_cancel is False
    assert store.load(use_case.thread_id_for(_job())).status == JobStatus.cancelled.value


@pytest.mark.asyncio
async def test_resume_can_raise_workflow_cancelled(tmp_path: Path) -> None:
    class _CancellingWorkflow:
        async def run(self, job: JobDefinition) -> object:
            raise asyncio.CancelledError

    use_case = ResumeJobUseCase(
        checkpoint_store=SQLiteCheckpointStore(database_path=tmp_path / "checkpoints.sqlite3"),
        workflow=_CancellingWorkflow(),
        graph_kind=WorkflowGraphKind.translation_quality,
        revision_id="mock-revision-1",
        raise_on_cancel=True,
    )

    with pytest.raises(WorkflowCancelled):
        await use_case.resume(_job())
