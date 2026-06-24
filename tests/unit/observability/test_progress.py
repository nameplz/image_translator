from __future__ import annotations

from image_translator.domain import JobStatus
from image_translator.observability.progress import ProgressMapper


def test_progress_mapper_uses_documented_phase_weights_and_never_decreases() -> None:
    mapper = ProgressMapper()

    snapshots = (
        mapper.map_update(
            job_id="job-1",
            update={"stage": "translation", "status": "translating", "step_progress": 0.5},
        ),
        mapper.map_update(
            job_id="job-1",
            update={"stage": "ocr", "status": "ocr_running", "step_progress": 1.0},
        ),
        mapper.map_update(
            job_id="job-1",
            update={"stage": "result_quality", "status": "reviewing_result"},
        ),
    )

    assert snapshots[0].progress == 0.48
    assert snapshots[1].progress == 0.48
    assert snapshots[2].progress == 0.88
    assert tuple(snapshot.progress for snapshot in snapshots) == tuple(
        sorted(snapshot.progress for snapshot in snapshots)
    )


def test_progress_mapper_preserves_interrupt_progress_and_summary() -> None:
    mapper = ProgressMapper()
    mapper.map_update(
        job_id="job-1",
        update={"stage": "translation_review", "status": "reviewing_translation"},
    )

    snapshot = mapper.map_update(
        job_id="job-1",
        update={
            "stage": "translation_review",
            "status": "waiting_for_user",
            "interrupt_summary": "review region-2",
        },
    )

    assert snapshot.status is JobStatus.waiting_for_user
    assert snapshot.progress == 0.58
    assert snapshot.interrupt_summary == "review region-2"


def test_progress_mapper_maps_cancelled_update_to_cancelled_snapshot() -> None:
    mapper = ProgressMapper()

    snapshot = mapper.map_update(
        job_id="job-1",
        update={"stage": "translation", "status": "cancelled", "message": "Cancelled"},
    )

    assert snapshot.status is JobStatus.cancelled
    assert snapshot.can_cancel is False
    assert snapshot.message == "Cancelled"
