"""
Notification domain models for Phase 21 automation.

Defines notification types, channel types, contact targets, preferences,
and notification payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class NotificationType(str, Enum):
    """Types of notifications the automation layer can emit."""
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    MANUAL_TRIGGER = "manual_trigger"
    MANUAL_RESCAN = "manual_rescan"
    HIGH_PRIORITY_OPPORTUNITY = "high_priority_opportunity"
    STATE_CHANGE = "state_change"
    DECISION_UPDATED = "decision_updated"
    PROVIDER_WARNING = "provider_warning"
    DAILY_DIGEST = "daily_digest"
    RUN_QUEUE_STUCK = "run_queue_stuck"


class NotificationSeverity(str, Enum):
    """Severity levels for notifications."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SIGNAL = "signal"


class ChannelType(str, Enum):
    """Supported notification channel types."""
    EMAIL = "email"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    SLACK = "slack"
    DISCORD = "discord"
    WEBHOOK = "webhook"


@dataclass
class ContactTarget:
    """A configured contact/target for a notification channel."""
    channel_type: str
    target_value: str  # email address, chat_id, webhook URL, etc.
    label: str = ""
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_type": self.channel_type,
            "target_value": self.target_value,
            "label": self.label,
            "enabled": self.enabled,
        }

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialise with masked target value for UI/logs."""
        masked = self._mask_value(self.target_value)
        return {
            "channel_type": self.channel_type,
            "target_value": masked,
            "label": self.label,
            "enabled": self.enabled,
        }

    @staticmethod
    def _mask_value(value: str) -> str:
        if not value:
            return ""
        if len(value) <= 4:
            return "••••"
        return "•" * (len(value) - 4) + value[-4:]


@dataclass
class ChannelPreference:
    """Per-channel preference configuration."""
    channel_type: str
    enabled: bool = False
    digest_mode: bool = False  # batch into digest vs instant

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_type": self.channel_type,
            "enabled": self.enabled,
            "digest_mode": self.digest_mode,
        }


@dataclass
class TypePreference:
    """Per-notification-type preference configuration."""
    notification_type: str
    enabled: bool = True
    min_severity: str = NotificationSeverity.INFO.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "notification_type": self.notification_type,
            "enabled": self.enabled,
            "min_severity": self.min_severity,
        }


@dataclass
class NotificationPreferences:
    """User notification preferences for all channels and types."""
    channels: list[ChannelPreference] = field(default_factory=list)
    types: list[TypePreference] = field(default_factory=list)
    contacts: list[ContactTarget] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channels": [c.to_dict() for c in self.channels],
            "types": [t.to_dict() for t in self.types],
            "contacts": [c.to_dict() for c in self.contacts],
        }

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialise with masked contact targets for UI/logs."""
        return {
            "channels": [c.to_dict() for c in self.channels],
            "types": [t.to_dict() for t in self.types],
            "contacts": [c.to_safe_dict() for c in self.contacts],
        }

    def is_channel_enabled(self, channel_type: str) -> bool:
        for ch in self.channels:
            if ch.channel_type == channel_type:
                return ch.enabled
        return False

    def is_type_enabled(self, notification_type: str) -> bool:
        for tp in self.types:
            if tp.notification_type == notification_type:
                return tp.enabled
        return True  # default to enabled if not explicitly configured

    def get_contacts_for_channel(self, channel_type: str) -> list[ContactTarget]:
        return [
            c for c in self.contacts
            if c.channel_type == channel_type and c.enabled
        ]


@dataclass
class Notification:
    """A notification payload ready for dispatch."""
    notification_id: str = field(default_factory=lambda: uuid4().hex[:12])
    notification_type: str = NotificationType.JOB_STARTED.value
    severity: str = NotificationSeverity.INFO.value
    title: str = ""
    message: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    artifact_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "notification_id": self.notification_id,
            "notification_type": self.notification_type,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp,
            "artifact_refs": list(self.artifact_refs),
            "metadata": dict(self.metadata),
        }


def default_notification_preferences() -> NotificationPreferences:
    """Return default preferences with all channels disabled, all types enabled."""
    channels = [
        ChannelPreference(channel_type=ct.value, enabled=False)
        for ct in ChannelType
    ]
    types = [
        TypePreference(notification_type=nt.value, enabled=True)
        for nt in NotificationType
    ]
    return NotificationPreferences(channels=channels, types=types, contacts=[])
