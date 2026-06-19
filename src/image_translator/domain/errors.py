from __future__ import annotations


class DomainError(Exception):
    """Base class for typed domain errors."""


class ImageLoadError(DomainError):
    """Raised when an input image cannot be loaded or validated."""


class InvalidRegionError(DomainError):
    """Raised when region geometry, ID, or structure is invalid."""


class ReadingOrderUncertainError(DomainError):
    """Raised when reading order cannot be safely resolved automatically."""


class ProviderConfigError(DomainError):
    """Raised when configured provider capabilities do not satisfy a job."""


class ProviderCallError(DomainError):
    """Raised when a provider call fails at the domain boundary."""


class TranslationResultMismatchError(DomainError):
    """Raised when translation output does not match requested regions."""


class QualityGateRejected(DomainError):
    """Raised when a quality gate rejects automatic approval."""


class RevisionPlanRejected(DomainError):
    """Raised when a proposed revision plan is invalid or unapproved."""


class ExportBlockedError(DomainError):
    """Raised when unresolved blocking issues prevent normal export."""


class WorkflowCancelled(DomainError):
    """Raised when a workflow is cancelled by the user."""


class CheckpointError(DomainError):
    """Raised when workflow checkpoint persistence fails."""
