"""Audiensi Conversation Manager — orchestrates audiensi conversations."""

from __future__ import annotations

import json

from orchestrator.config import log, cfg
from orchestrator.audiensi.react_agent import AudiensiReactAgent
from orchestrator import db


class AudiensiConversationManager:
    """Manages audiensi conversation lifecycle."""

    def __init__(self) -> None:
        self._agent = AudiensiReactAgent()

    async def generate_initial_message(
        self, university_name: str, rector_name: str | None = None,
        contact_name: str | None = None,
    ) -> str:
        """Generate the first audiensi outreach message."""
        return await self._agent.generate_initial_message(
            university_name, rector_name=rector_name, contact_name=contact_name,
        )

    async def process_incoming_message(
        self, phone: str, message: str, push_name: str = "",
    ) -> dict:
        """Process incoming WA message for audiensi conversations."""
        result = await self._agent.process_incoming_message(phone, message, push_name)
        return {
            "action": result.action.value,
            "response_message": result.response_message,
            "conversation_state": result.conversation_state,
        }

    async def generate_followup(
        self, audiensi: dict, attempt: int,
    ) -> str:
        """Generate audiensi follow-up message."""
        return await self._agent.generate_followup(audiensi, attempt)


# Singleton
audiensi_conversation_manager = AudiensiConversationManager()
