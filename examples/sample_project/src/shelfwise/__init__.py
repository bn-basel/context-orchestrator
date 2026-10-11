"""Shelfwise: lending service for a community library."""


class ShelfwiseError(Exception):
    """Base class for domain errors."""


class LoanLimitExceeded(ShelfwiseError):
    pass


class AlreadyReturned(ShelfwiseError):
    pass
