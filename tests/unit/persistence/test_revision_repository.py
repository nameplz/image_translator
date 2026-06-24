from __future__ import annotations

import pytest

from image_translator.domain.revision import (
    ApprovalRecord,
    RevisionAction,
    RevisionDomainDiff,
    RevisionPlan,
    RevisionProposal,
    RevisionRecord,
    RevisionScope,
    RevisionTarget,
    approve_revision_plan,
)
from image_translator.persistence.revision_repository import (
    AppendOnlyRevisionRepository,
    RevisionRepositoryError,
)


def test_completed_revisions_are_append_only_and_active_pointer_moves() -> None:
    repository = AppendOnlyRevisionRepository()
    first = _record("revision-1", parent_revision_id=None)
    second = _record("revision-2", parent_revision_id="revision-1")

    repository.append(first)
    repository.append(second)

    assert repository.list_revisions() == (first, second)
    assert repository.active_revision_id == "revision-2"

    repository.undo()
    assert repository.active_revision_id == "revision-1"
    assert repository.list_revisions() == (first, second)

    repository.redo()
    assert repository.active_revision_id == "revision-2"
    assert repository.list_revisions() == (first, second)


def test_duplicate_revision_id_is_rejected_without_mutating_history() -> None:
    repository = AppendOnlyRevisionRepository()
    first = _record("revision-1", parent_revision_id=None)
    repository.append(first)

    with pytest.raises(RevisionRepositoryError, match="already exists"):
        repository.append(_record("revision-1", parent_revision_id=None))

    assert repository.list_revisions() == (first,)
    assert repository.active_revision_id == "revision-1"


def test_redo_stack_is_cleared_by_new_branch() -> None:
    repository = AppendOnlyRevisionRepository()
    first = _record("revision-1", parent_revision_id=None)
    second = _record("revision-2", parent_revision_id="revision-1")
    branch = _record("revision-3", parent_revision_id="revision-1")
    repository.append(first)
    repository.append(second)
    repository.undo()

    repository.append(branch)

    assert repository.active_revision_id == "revision-3"
    assert repository.redo() is None
    assert repository.list_revisions() == (first, second, branch)


def _record(revision_id: str, *, parent_revision_id: str | None) -> RevisionRecord:
    plan = approve_revision_plan(
        RevisionPlan(
            plan_id=f"plan-{revision_id}",
            base_revision_id=parent_revision_id or "root",
            normalized_user_instruction="make this more polite",
            target=RevisionTarget(
                region_ids=("region-1",),
                target_scope=RevisionScope.current_region,
                resolution_evidence=("selected region",),
            ),
            actions=(RevisionAction.adjust_tone,),
            proposals=(
                RevisionProposal(
                    action=RevisionAction.adjust_tone,
                    before="current translation",
                    after="more polite translation",
                ),
            ),
            required_validation=("translation_quality",),
        ),
        approval_record=ApprovalRecord(
            approval_id=f"approval-{revision_id}",
            approved_by="user",
            approved_at="2026-06-24T12:00:00+00:00",
        ),
    )
    return RevisionRecord(
        revision_id=revision_id,
        parent_revision_id=parent_revision_id,
        approved_plan=plan,
        domain_diff=(
            RevisionDomainDiff(
                action=RevisionAction.adjust_tone,
                region_ids=("region-1",),
                summary="tone adjusted",
            ),
        ),
        validation_results=("translation_quality:passed",),
        created_at="2026-06-24T12:01:00+00:00",
        approval_record=plan.approval_record,
    )
