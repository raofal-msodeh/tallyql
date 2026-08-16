"""Exception hierarchy for TallyQL."""

from __future__ import annotations


class TallyQLError(Exception):
    """Base class for all TallyQL errors."""


class PipelineError(TallyQLError):
    """The pipeline could not produce results (all lines bad / no matches)."""


class InputError(TallyQLError):
    """A provided input path cannot be used (missing, unreadable, traversal)."""


class ConfigError(TallyQLError):
    """A user-provided filter/aggregate/option is malformed."""
