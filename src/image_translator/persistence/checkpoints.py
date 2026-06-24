from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeAlias

from pydantic import BaseModel

from image_translator.config.resources import app_data_path
from image_translator.domain.errors import CheckpointError
from image_translator.domain.ids import JobId, RevisionId, WorkflowThreadId

CHECKPOINT_SCHEMA_VERSION = 1
DEFAULT_CHECKPOINT_DATABASE_NAME = "checkpoints.sqlite3"

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]

_FORBIDDEN_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "provider_raw_payload",
    "raw_provider_payload",
    "raw_payload",
    "raw_response",
    "full_prompt",
    "prompt",
    "image_array",
    "image_bytes",
    "crop_bytes",
    "crop_data",
)


class WorkflowGraphKind(StrEnum):
    translation_quality = "translation_quality"
    result_quality = "result_quality"
    natural_revision = "natural_revision"


@dataclass(frozen=True, slots=True)
class WorkflowCheckpoint:
    thread_id: WorkflowThreadId
    job_id: JobId
    revision_id: RevisionId
    graph_kind: WorkflowGraphKind
    status: str
    state: Mapping[str, Any]
    schema_version: int = CHECKPOINT_SCHEMA_VERSION
    updated_at: datetime | None = None


def workflow_thread_id(
    *,
    job_id: JobId,
    revision_id: RevisionId,
    graph_kind: WorkflowGraphKind,
) -> WorkflowThreadId:
    return f"{job_id}:{revision_id}:{graph_kind.value}"


def default_checkpoint_database_path(app_name: str = "Image Translator") -> Path:
    return app_data_path(DEFAULT_CHECKPOINT_DATABASE_NAME, app_name=app_name)


class SQLiteCheckpointStore:
    def __init__(self, database_path: Path | None = None) -> None:
        self.database_path = database_path or default_checkpoint_database_path()
        self._ensure_database()

    def save(self, checkpoint: WorkflowCheckpoint) -> WorkflowCheckpoint:
        if checkpoint.schema_version != CHECKPOINT_SCHEMA_VERSION:
            raise CheckpointError(
                f"unsupported checkpoint schema version: {checkpoint.schema_version}"
            )
        sanitized_state = sanitize_checkpoint_state(checkpoint.state)
        if not isinstance(sanitized_state, dict):
            raise CheckpointError("checkpoint root state must be a JSON object")
        updated_at = checkpoint.updated_at or datetime.now(UTC)
        payload = json.dumps(sanitized_state, sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_checkpoints (
                    thread_id,
                    job_id,
                    revision_id,
                    graph_kind,
                    schema_version,
                    status,
                    state_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    job_id = excluded.job_id,
                    revision_id = excluded.revision_id,
                    graph_kind = excluded.graph_kind,
                    schema_version = excluded.schema_version,
                    status = excluded.status,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (
                    checkpoint.thread_id,
                    checkpoint.job_id,
                    checkpoint.revision_id,
                    checkpoint.graph_kind.value,
                    CHECKPOINT_SCHEMA_VERSION,
                    checkpoint.status,
                    payload,
                    updated_at.isoformat(),
                ),
            )
        return WorkflowCheckpoint(
            thread_id=checkpoint.thread_id,
            job_id=checkpoint.job_id,
            revision_id=checkpoint.revision_id,
            graph_kind=checkpoint.graph_kind,
            status=checkpoint.status,
            state=sanitized_state,
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            updated_at=updated_at,
        )

    def load(self, thread_id: WorkflowThreadId) -> WorkflowCheckpoint | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT thread_id, job_id, revision_id, graph_kind, schema_version, status,
                       state_json, updated_at
                FROM workflow_checkpoints
                WHERE thread_id = ?
                """,
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        return _checkpoint_from_row(row)

    def load_for_job(
        self,
        *,
        job_id: JobId,
        revision_id: RevisionId | None = None,
    ) -> tuple[WorkflowCheckpoint, ...]:
        params: tuple[str, ...]
        query = """
            SELECT thread_id, job_id, revision_id, graph_kind, schema_version, status,
                   state_json, updated_at
            FROM workflow_checkpoints
            WHERE job_id = ?
        """
        if revision_id is None:
            params = (job_id,)
        else:
            query += " AND revision_id = ?"
            params = (job_id, revision_id)
        query += " ORDER BY updated_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return tuple(_checkpoint_from_row(row) for row in rows)

    def record_provider_call_completed(
        self,
        *,
        thread_id: WorkflowThreadId,
        request_fingerprint: str,
        result_summary: Mapping[str, Any] | None = None,
    ) -> None:
        summary = sanitize_checkpoint_state(result_summary or {})
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO provider_call_fingerprints (
                    thread_id,
                    request_fingerprint,
                    schema_version,
                    result_summary_json,
                    completed_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    request_fingerprint,
                    CHECKPOINT_SCHEMA_VERSION,
                    json.dumps(summary, sort_keys=True, separators=(",", ":")),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def has_completed_provider_call(
        self,
        *,
        thread_id: WorkflowThreadId,
        request_fingerprint: str,
    ) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM provider_call_fingerprints
                WHERE thread_id = ? AND request_fingerprint = ?
                LIMIT 1
                """,
                (thread_id, request_fingerprint),
            ).fetchone()
        return row is not None

    def completed_provider_fingerprints(
        self,
        thread_id: WorkflowThreadId,
    ) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT request_fingerprint
                FROM provider_call_fingerprints
                WHERE thread_id = ?
                ORDER BY completed_at ASC
                """,
                (thread_id,),
            ).fetchall()
        return tuple(str(row["request_fingerprint"]) for row in rows)

    def _ensure_database(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        _chmod_user_only(self.database_path.parent, directory=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                    thread_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    graph_kind TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_checkpoints_job
                    ON workflow_checkpoints(job_id, revision_id, graph_kind);

                CREATE TABLE IF NOT EXISTS provider_call_fingerprints (
                    thread_id TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    result_summary_json TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    PRIMARY KEY (thread_id, request_fingerprint)
                );
                """
            )
        _chmod_user_only(self.database_path, directory=False)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection


def sanitize_checkpoint_state(value: Any) -> JSONValue:
    sanitized = _sanitize(value, key_hint=None)
    _assert_json_safe(sanitized)
    return sanitized


def _sanitize(value: Any, *, key_hint: str | None) -> JSONValue:
    if key_hint is not None and _is_forbidden_key(key_hint):
        return None
    if isinstance(value, BaseModel):
        return _sanitize(value.model_dump(mode="json"), key_hint=key_hint)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str | int | bool) or value is None:
        return value
    if isinstance(value, float):
        json.dumps(value, allow_nan=False)
        return value
    if isinstance(value, bytes | bytearray | memoryview):
        return None
    if _is_numpy_array(value) or _is_pil_image(value):
        return None
    if isinstance(value, Mapping):
        sanitized_dict: dict[str, JSONValue] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if _is_forbidden_key(key):
                continue
            child = _sanitize(raw_value, key_hint=key)
            if child is not None:
                sanitized_dict[key] = child
        return sanitized_dict
    if isinstance(value, tuple | list):
        return [
            child
            for item in value
            if (child := _sanitize(item, key_hint=key_hint)) is not None
        ]
    raise TypeError(
        "checkpoint state contains unsupported value "
        f"{type(value).__module__}.{type(value).__qualname__}"
    )


def _assert_json_safe(value: JSONValue) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TypeError("checkpoint state must be JSON serializable") from exc


def _checkpoint_from_row(row: sqlite3.Row) -> WorkflowCheckpoint:
    schema_version = int(row["schema_version"])
    if schema_version != CHECKPOINT_SCHEMA_VERSION:
        raise CheckpointError(f"unsupported checkpoint schema version: {schema_version}")
    return WorkflowCheckpoint(
        thread_id=str(row["thread_id"]),
        job_id=str(row["job_id"]),
        revision_id=str(row["revision_id"]),
        graph_kind=WorkflowGraphKind(str(row["graph_kind"])),
        status=str(row["status"]),
        state=json.loads(str(row["state_json"])),
        schema_version=schema_version,
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )


def _is_forbidden_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(fragment in normalized for fragment in _FORBIDDEN_KEY_FRAGMENTS)


def _is_numpy_array(value: Any) -> bool:
    value_type = type(value)
    return value_type.__module__.startswith("numpy") and value_type.__name__ == "ndarray"


def _is_pil_image(value: Any) -> bool:
    value_type = type(value)
    return value_type.__module__.startswith("PIL.") and value_type.__name__ == "Image"


def _chmod_user_only(path: Path, *, directory: bool) -> None:
    try:
        path.chmod(0o700 if directory else 0o600)
    except OSError:
        return


__all__ = [
    "CHECKPOINT_SCHEMA_VERSION",
    "DEFAULT_CHECKPOINT_DATABASE_NAME",
    "SQLiteCheckpointStore",
    "WorkflowCheckpoint",
    "WorkflowGraphKind",
    "default_checkpoint_database_path",
    "sanitize_checkpoint_state",
    "workflow_thread_id",
]
