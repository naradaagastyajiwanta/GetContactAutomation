from enum import Enum


class AudiensiState(str, Enum):
    QUEUED = "QUEUED"
    APPROVED = "APPROVED"
    INITIAL_SENT = "INITIAL_SENT"
    WAITING_REPLY = "WAITING_REPLY"
    REPLIED = "REPLIED"
    ANALYZING = "ANALYZING"
    SCHEDULING = "SCHEDULING"
    SCHEDULED = "SCHEDULED"
    ZOOM_SENT = "ZOOM_SENT"
    NEED_MORE = "NEED_MORE"
    FOLLOWUP_SENT = "FOLLOWUP_SENT"
    REFUSED = "REFUSED"
    NO_REPLY = "NO_REPLY"
    ABANDONED = "ABANDONED"

    @classmethod
    def terminal_states(cls) -> set[str]:
        return {cls.ZOOM_SENT, cls.REFUSED, cls.ABANDONED}
