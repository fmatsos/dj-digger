"""Stable, presentation-independent application errors."""


class CoreError(Exception):
    """Base class for expected application failures."""


class InvalidInputError(CoreError):
    """A request contains invalid or contradictory input."""


class ResourceNotFoundError(CoreError):
    """A requested source or packaged resource is unavailable."""


class StateConflictError(CoreError):
    """A request conflicts with current catalog state."""


class DependencyError(CoreError):
    """A required local dependency failed."""


class DependencyTimeoutError(DependencyError):
    """A required dependency exceeded its time budget."""


class IntegrityError(CoreError):
    """The catalog or an output artifact failed an integrity check."""
