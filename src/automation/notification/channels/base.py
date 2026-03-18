"""
Base notification channel ABC and placeholder adapters.

All channels implement send() -> NotificationResult. Placeholder channels
for WhatsApp, Slack, Discord, and Webhook raise NotImplementedError with
clear messages indicating they are reserved for future phases.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from src.automation.notification.models import Notification


@dataclass
class NotificationResult:
    """Result of a notification send attempt."""
    success: bool
    channel: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    error_message: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "channel": self.channel,
            "timestamp": self.timestamp,
            "error_message": self.error_message,
            "metadata": dict(self.metadata),
        }


class BaseNotificationChannel(ABC):
    """Abstract base class for notification channel adapters."""

    @property
    @abstractmethod
    def channel_type(self) -> str:
        """Return the ChannelType value string for this adapter."""
        ...

    @abstractmethod
    def send(
        self,
        notification: Notification,
        target: str,
        **kwargs: Any,
    ) -> NotificationResult:
        """Send a notification to the given target.

        Args:
            notification: The notification payload.
            target: Channel-specific target (email, chat_id, webhook URL, etc.)
            **kwargs: Additional channel-specific parameters.

        Returns:
            NotificationResult indicating success/failure.
        """
        ...


# ---------------------------------------------------------------------------
# Placeholder adapters for future channels
# ---------------------------------------------------------------------------

class WhatsAppChannel(BaseNotificationChannel):
    """WhatsApp notification channel — placeholder for future implementation."""

    @property
    def channel_type(self) -> str:
        return "whatsapp"

    def send(self, notification: Notification, target: str, **kwargs: Any) -> NotificationResult:
        return NotificationResult(
            success=False,
            channel=self.channel_type,
            error_message="WhatsApp channel is not yet implemented. Reserved for future phase.",
        )


class SlackChannel(BaseNotificationChannel):
    """Slack notification channel — placeholder for future implementation."""

    @property
    def channel_type(self) -> str:
        return "slack"

    def send(self, notification: Notification, target: str, **kwargs: Any) -> NotificationResult:
        return NotificationResult(
            success=False,
            channel=self.channel_type,
            error_message="Slack channel is not yet implemented. Reserved for future phase.",
        )


class DiscordChannel(BaseNotificationChannel):
    """Discord notification channel — placeholder for future implementation."""

    @property
    def channel_type(self) -> str:
        return "discord"

    def send(self, notification: Notification, target: str, **kwargs: Any) -> NotificationResult:
        return NotificationResult(
            success=False,
            channel=self.channel_type,
            error_message="Discord channel is not yet implemented. Reserved for future phase.",
        )


class WebhookChannel(BaseNotificationChannel):
    """Generic webhook channel — placeholder for future implementation."""

    @property
    def channel_type(self) -> str:
        return "webhook"

    def send(self, notification: Notification, target: str, **kwargs: Any) -> NotificationResult:
        return NotificationResult(
            success=False,
            channel=self.channel_type,
            error_message="Webhook channel is not yet implemented. Reserved for future phase.",
        )
