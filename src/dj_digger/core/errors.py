"""Stable, presentation-independent domain errors.

Each class carries the failure class persisted in run logs. Deriving it from
the exception type — rather than matching substrings in the message — keeps
diagnostics stable when a message is reworded, and keeps private library
detail out of persisted facts.

Expected failures also inherit the builtin kind callers already catch
(``ValueError`` for rejected input, ``RuntimeError`` for conflicting state),
so adopting the hierarchy never breaks an existing ``except`` clause.
"""

UNCLASSIFIED = "operation failed"


class CoreError(Exception):
    """Base class for expected application failures."""

    classification = UNCLASSIFIED


class InvalidInputError(CoreError, ValueError):
    """A request contains invalid or contradictory input."""

    classification = "invalid input"


class ResourceNotFoundError(CoreError, ValueError):
    """A requested source or packaged resource is unavailable."""

    classification = "unavailable"


class StateConflictError(CoreError, RuntimeError):
    """A request conflicts with current catalog state."""

    classification = "state conflict"


class DependencyError(CoreError, RuntimeError):
    """A required local dependency failed."""

    classification = "dependency unavailable"


class DependencyTimeoutError(DependencyError):
    """A required dependency exceeded its time budget."""

    classification = "timeout"


class IntegrityError(CoreError, RuntimeError):
    """The catalog or an output artifact failed an integrity check."""

    classification = "integrity"


class StaleReferenceError(CoreError, RuntimeError):
    """A referenced catalog row no longer matches the stored state."""

    classification = "stale"


def classify(error: object) -> str:
    """Return the safe, stable failure class for one exception."""
    if isinstance(error, CoreError):
        return error.classification
    return UNCLASSIFIED


__all__ = [
    "UNCLASSIFIED",
    "CoreError",
    "DependencyError",
    "DependencyTimeoutError",
    "IntegrityError",
    "InvalidInputError",
    "ResourceNotFoundError",
    "StaleReferenceError",
    "StateConflictError",
    "classify",
]
