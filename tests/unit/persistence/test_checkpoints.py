from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import BaseModel

from image_translator.persistence.checkpoints import (
    CHECKPOINT_SCHEMA_VERSION,
    SQLiteCheckpointStore,
    WorkflowCheckpoint,
    WorkflowGraphKind,
    sanitize_checkpoint_state,
    workflow_thread_id,
)


class _ProviderDTO(BaseModel):
    provider_id: str
    request_fingerprint: str
    safe_metadata_summary: tuple[str, ...] = ()


def test_checkpoint_store_saves_schema_version_and_json_state(tmp_path: Path) -> None:
    store = SQLiteCheckpointStore(database_path=tmp_path / "checkpoints.sqlite3")
    thread_id = workflow_thread_id(
        job_id="job-1",
        revision_id="revision-1",
        graph_kind=WorkflowGraphKind.translation_quality,
    )

    store.save(
        WorkflowCheckpoint(
            thread_id=thread_id,
            job_id="job-1",
            revision_id="revision-1",
            graph_kind=WorkflowGraphKind.translation_quality,
            status="running",
            state={"provider": _ProviderDTO(provider_id="mock", request_fingerprint="fp-1")},
        )
    )

    loaded = store.load(thread_id)

    assert loaded is not None
    assert loaded.schema_version == CHECKPOINT_SCHEMA_VERSION
    assert loaded.thread_id == thread_id
    assert loaded.state == {
        "provider": {
            "provider_id": "mock",
            "request_fingerprint": "fp-1",
            "safe_metadata_summary": [],
        }
    }


def test_checkpoint_redacts_forbidden_payloads_before_sqlite_write(tmp_path: Path) -> None:
    store = SQLiteCheckpointStore(database_path=tmp_path / "checkpoints.sqlite3")
    forbidden_state = {
        "safe": {"stage": "translation"},
        "api_key": "sk-test-secret",
        "provider_raw_payload": {"text": "raw response containing user text"},
        "full_prompt": "translate the full private prompt",
        "image_array": np.array([[1, 2, 3]]),
        "crop_bytes": b"image bytes",
        "input_path": Path("/safe/local/input.png"),
    }

    store.save(
        WorkflowCheckpoint(
            thread_id="job-1:revision-1:translation_quality",
            job_id="job-1",
            revision_id="revision-1",
            graph_kind=WorkflowGraphKind.translation_quality,
            status="running",
            state=forbidden_state,
        )
    )

    loaded = store.load("job-1:revision-1:translation_quality")

    assert loaded is not None
    serialized = repr(loaded.state)
    assert loaded.state == {
        "safe": {"stage": "translation"},
        "input_path": "/safe/local/input.png",
    }
    assert "sk-test-secret" not in serialized
    assert "raw response" not in serialized
    assert "full private prompt" not in serialized
    assert "image bytes" not in serialized


def test_sanitize_checkpoint_state_rejects_non_json_safe_values() -> None:
    class Unsupported:
        pass

    with pytest.raises(TypeError, match="checkpoint state contains unsupported value"):
        sanitize_checkpoint_state({"unsupported": Unsupported()})


def test_provider_fingerprint_completion_is_scoped_to_thread(tmp_path: Path) -> None:
    store = SQLiteCheckpointStore(database_path=tmp_path / "checkpoints.sqlite3")

    store.record_provider_call_completed(
        thread_id="job-1:revision-1:translation_quality",
        request_fingerprint="fp-complete",
        result_summary={"provider_id": "mock-translator"},
    )

    assert store.has_completed_provider_call(
        thread_id="job-1:revision-1:translation_quality",
        request_fingerprint="fp-complete",
    )
    assert not store.has_completed_provider_call(
        thread_id="job-1:revision-1:result_quality",
        request_fingerprint="fp-complete",
    )
