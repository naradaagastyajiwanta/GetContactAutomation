"""Custom exceptions for the marketing module."""


class QuotaExhaustedException(Exception):
    """Raised when AI API quota/credit is fully exhausted (not just rate-limited).

    This signals that ALL retries should be abandoned and the group should be
    stopped — retrying will not help until the user tops up credits.
    """
    pass
