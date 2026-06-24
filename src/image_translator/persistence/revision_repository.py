from __future__ import annotations

from image_translator.domain.ids import RevisionId
from image_translator.domain.revision import RevisionRecord


class RevisionRepositoryError(Exception):
    """Raised when revision history cannot preserve append-only semantics."""


class AppendOnlyRevisionRepository:
    def __init__(self) -> None:
        self._records: tuple[RevisionRecord, ...] = ()
        self._active_revision_id: RevisionId | None = None
        self._redo_stack: tuple[RevisionId, ...] = ()

    @property
    def active_revision_id(self) -> RevisionId | None:
        return self._active_revision_id

    def append(self, record: RevisionRecord) -> None:
        if self.get(record.revision_id) is not None:
            raise RevisionRepositoryError(f"revision already exists: {record.revision_id}")
        if record.parent_revision_id is not None and self.get(record.parent_revision_id) is None:
            raise RevisionRepositoryError(
                f"parent revision does not exist: {record.parent_revision_id}"
            )
        self._records = (*self._records, record)
        self._active_revision_id = record.revision_id
        self._redo_stack = ()

    def get(self, revision_id: RevisionId) -> RevisionRecord | None:
        return next(
            (record for record in self._records if record.revision_id == revision_id),
            None,
        )

    def list_revisions(self) -> tuple[RevisionRecord, ...]:
        return self._records

    def undo(self) -> RevisionId | None:
        if self._active_revision_id is None:
            return None
        active_record = self.get(self._active_revision_id)
        if active_record is None or active_record.parent_revision_id is None:
            return None
        self._redo_stack = (self._active_revision_id, *self._redo_stack)
        self._active_revision_id = active_record.parent_revision_id
        return self._active_revision_id

    def redo(self) -> RevisionId | None:
        if not self._redo_stack:
            return None
        next_revision_id = self._redo_stack[0]
        self._redo_stack = self._redo_stack[1:]
        self._active_revision_id = next_revision_id
        return self._active_revision_id

    def set_active_revision(self, revision_id: RevisionId) -> None:
        if self.get(revision_id) is None:
            raise RevisionRepositoryError(f"revision does not exist: {revision_id}")
        self._active_revision_id = revision_id
        self._redo_stack = ()


__all__ = [
    "AppendOnlyRevisionRepository",
    "RevisionRepositoryError",
]
