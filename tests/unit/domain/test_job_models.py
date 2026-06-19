from __future__ import annotations

import pytest
from pydantic import ValidationError

from image_translator.domain.job import JobDefinition, JobSnapshot, JobStatus


def test_job_snapshot_progress_must_be_between_zero_and_one() -> None:
    with pytest.raises(ValidationError):
        JobSnapshot(
            job_id="job-1",
            status=JobStatus.translating,
            progress=-0.01,
            stage="translation",
            message="Translating regions",
        )

    with pytest.raises(ValidationError):
        JobSnapshot(
            job_id="job-1",
            status=JobStatus.translating,
            progress=1.01,
            stage="translation",
            message="Translating regions",
        )


def test_job_snapshot_is_immutable() -> None:
    snapshot = JobSnapshot(
        job_id="job-1",
        status=JobStatus.queued,
        progress=0.0,
        stage="queued",
        message="Ready",
    )

    with pytest.raises(ValidationError):
        snapshot.progress = 0.5


def test_job_definition_uses_tuple_based_provider_collections() -> None:
    definition = JobDefinition(
        job_id="job-1",
        project_id="project-1",
        input_path="/tmp/input.png",
        requested_output_path="/tmp/output.png",
        source_language="ja",
        target_language="ko",
        provider_selection=["primary-ocr", "translator-a", "reviewer-b"],
        fallback_order=["translator-b"],
        visual_mode=False,
        image_transmission_consent=False,
        processing_profile="quality",
    )

    assert definition.provider_selection == ("primary-ocr", "translator-a", "reviewer-b")
    assert definition.fallback_order == ("translator-b",)
