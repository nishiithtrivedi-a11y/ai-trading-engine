"""
Notification service — dispatches notifications to enabled channels.

Loads user preferences from file-based config, routes notifications to
the appropriate channel adapters, and logs results without exposing secrets.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.automation.notification.channels.base import (
    BaseNotificationChannel,
    NotificationResult,
)
from src.automation.notification.channels.email_channel import EmailChannel
from src.automation.notification.channels.telegram_channel import TelegramChannel
from src.automation.notification.channels.base import (
    WhatsAppChannel,
    SlackChannel,
    DiscordChannel,
    WebhookChannel,
)
from src.automation.notification.models import (
    ChannelPreference,
    ChannelType,
    ContactTarget,
    Notification,
    NotificationPreferences,
    NotificationType,
    TypePreference,
    default_notification_preferences,
)

logger = logging.getLogger("notification_service")


@dataclass
class NotificationService:
    """Dispatches notifications to configured channels per user preferences."""

    preferences_path: Path = field(
        default_factory=lambda: Path("config/notification_preferences.json")
    )
    _preferences: Optional[NotificationPreferences] = field(default=None, repr=False)
    _channels: dict[str, BaseNotificationChannel] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        # Register all channel adapters
        self._channels = {
            ChannelType.EMAIL.value: EmailChannel(),
            ChannelType.TELEGRAM.value: TelegramChannel(),
            ChannelType.WHATSAPP.value: WhatsAppChannel(),
            ChannelType.SLACK.value: SlackChannel(),
            ChannelType.DISCORD.value: DiscordChannel(),
            ChannelType.WEBHOOK.value: WebhookChannel(),
        }

    def get_preferences(self) -> NotificationPreferences:
        """Load preferences from disk, returning defaults if missing."""
        if self._preferences is not None:
            return self._preferences
        self._preferences = self._load_preferences()
        return self._preferences

    def save_preferences(self, prefs: NotificationPreferences) -> Path:
        """Persist preferences to disk."""
        self._preferences = prefs
        self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
        self.preferences_path.write_text(
            json.dumps(prefs.to_dict(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        return self.preferences_path

    def send(self, notification: Notification) -> list[NotificationResult]:
        """Dispatch a notification to all enabled channels.

        Respects channel enable/disable, notification type enable/disable,
        and per-channel contact targets. Notification failures are logged
        but never propagated.
        """
        prefs = self.get_preferences()
        results: list[NotificationResult] = []

        # Check if this notification type is enabled
        if not prefs.is_type_enabled(notification.notification_type):
            logger.debug(
                "Notification type %s is disabled, skipping.",
                notification.notification_type,
            )
            return results

        # Dispatch to each enabled channel
        for channel_type, adapter in self._channels.items():
            if not prefs.is_channel_enabled(channel_type):
                continue

            contacts = prefs.get_contacts_for_channel(channel_type)
            if not contacts:
                logger.debug(
                    "Channel %s enabled but no contacts configured, skipping.",
                    channel_type,
                )
                continue

            for contact in contacts:
                try:
                    # Determine if digest mode
                    digest_mode = False
                    for ch_pref in prefs.channels:
                        if ch_pref.channel_type == channel_type:
                            digest_mode = ch_pref.digest_mode
                            break

                    result = adapter.send(
                        notification=notification,
                        target=contact.target_value,
                        digest_mode=digest_mode,
                    )
                    results.append(result)

                    # Log safely (no secrets)
                    if result.success:
                        logger.info(
                            "Notification sent via %s to %s: %s",
                            channel_type,
                            contact.to_safe_dict()["target_value"],
                            notification.title,
                        )
                    else:
                        logger.warning(
                            "Notification failed via %s: %s",
                            channel_type,
                            result.error_message,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Exception sending notification via %s: %s",
                        channel_type,
                        exc,
                    )
                    results.append(NotificationResult(
                        success=False,
                        channel=channel_type,
                        error_message=f"Exception: {exc}",
                    ))

        return results

    def send_test(self, channel_type: str) -> NotificationResult:
        """Send a test notification to verify a channel is working."""
        adapter = self._channels.get(channel_type)
        if adapter is None:
            return NotificationResult(
                success=False,
                channel=channel_type,
                error_message=f"Unknown channel type: {channel_type}",
            )

        prefs = self.get_preferences()
        contacts = prefs.get_contacts_for_channel(channel_type)
        if not contacts:
            return NotificationResult(
                success=False,
                channel=channel_type,
                error_message=f"No contacts configured for {channel_type}.",
            )

        test_notification = Notification(
            notification_type=NotificationType.JOB_COMPLETED.value,
            severity="info",
            title="Test Notification",
            message=f"This is a test notification from the AI Trading Engine via {channel_type}.",
            metadata={"test": True},
        )

        return adapter.send(
            notification=test_notification,
            target=contacts[0].target_value,
        )

    def create_notification_hook(self) -> Any:
        """Return a callable suitable for use as a scheduler notification hook."""
        def hook(notification_type: str, title: str, message: str, metadata: dict[str, Any]) -> None:
            notification = Notification(
                notification_type=notification_type,
                severity=_severity_for_type(notification_type),
                title=title,
                message=message,
                metadata=metadata,
            )
            self.send(notification)
        return hook

    def _load_preferences(self) -> NotificationPreferences:
        """Load preferences from JSON file, returning defaults if not found."""
        if not self.preferences_path.exists():
            return default_notification_preferences()

        try:
            data = json.loads(self.preferences_path.read_text(encoding="utf-8"))
            channels = [
                ChannelPreference(**ch) for ch in data.get("channels", [])
            ]
            types = [
                TypePreference(**tp) for tp in data.get("types", [])
            ]
            contacts = [
                ContactTarget(**ct) for ct in data.get("contacts", [])
            ]
            return NotificationPreferences(
                channels=channels, types=types, contacts=contacts,
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to load notification preferences: %s", exc)
            return default_notification_preferences()


def _severity_for_type(notification_type: str) -> str:
    """Map notification type to default severity."""
    error_types = {"job_failed", "run_queue_stuck"}
    warning_types = {"provider_warning"}
    signal_types = {"high_priority_opportunity"}

    if notification_type in error_types:
        return "error"
    if notification_type in warning_types:
        return "warning"
    if notification_type in signal_types:
        return "signal"
    return "info"
