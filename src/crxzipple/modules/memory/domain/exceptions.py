from __future__ import annotations


class MemoryValidationError(ValueError):
    pass


class MemoryCandidateNotFoundError(LookupError):
    pass


class MemoryEntryNotFoundError(LookupError):
    pass


class MemoryCandidateAlreadyReviewedError(RuntimeError):
    pass
