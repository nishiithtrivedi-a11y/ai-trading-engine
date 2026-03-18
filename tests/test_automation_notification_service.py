"""Tests for the notification service and channel adapters."""

from __future__ import annotations

import json
from pathlib import Path

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
from src.automation.notification.service import NotificationService
from src.automation.notification.channels.base import (
    WhatsAppChannel,
    SlackChannel,
    DiscordChannel,
    WebhookChannel,
)


def test_default_preferences_all_channels_disabled() -> None:
    prefs = default_notification_preferences()
    for ch in prefs.channels:
        assert ch.enabled is False


def test_default_preferences_all_types_enabled() -> None:
    prefs = default_notification_preferences()
    for tp in prefs.types:
        assert tp.enabled is True


def test_contact_target_masking() -> None:
    ct = ContactTarget(channel_type="email", target_value="user@example.com", label="Work")
    safe = ct.to_safe_dict()
    # should not contain the full email
    assert safe["target_value"] != "user@example.com"
    assert safe["target_value"].endswith(".com")
    assert "•" in safe["target_value"]


def test_notification_preferences_to_safe_dict() -> None:
    prefs = NotificationPreferences(
        channels=[ChannelPreference(channel_type="email", enabled=True)],
        types=[TypePreference(notification_type="job_started", enabled=True)],
        contacts=[ContactTarget(channel_type="email", target_value="secret@test.com")],
    )
    safe = prefs.to_safe_dict()
    assert "secret@test.com" not in json.dumps(safe)


def test_service_save_and_load_preferences(tmp_path: Path) -> None:
    prefs_path = tmp_path / "prefs.json"
    svc = NotificationService(preferences_path=prefs_path)

    prefs = NotificationPreferences(
        channels=[ChannelPreference(channel_type="email", enabled=True)],
        types=[TypePreference(notification_type="job_started", enabled=True)],
        contacts=[ContactTarget(channel_type="email", target_value="a@b.com", label="Test")],
    )
    svc.save_preferences(prefs)
    assert prefs_path.exists()

    # Reload
    svc2 = NotificationService(preferences_path=prefs_path)
    loaded = svc2.get_preferences()
    assert loaded.is_channel_enabled("email") is True
    assert len(loaded.contacts) == 1


def test_service_defaults_when_no_file(tmp_path: Path) -> None:
    svc = NotificationService(preferences_path=tmp_path / "nonexistent.json")
    prefs = svc.get_preferences()
    assert len(prefs.channels) == len(ChannelType)


def test_placeholder_channels_return_failure() -> None:
    notification = Notification(title="test", message="test message")
    for channel_cls in [WhatsAppChannel, SlackChannel, DiscordChannel, WebhookChannel]:
        ch = channel_cls()
        result = ch.send(notification, "target")
        assert result.success is False
        assert "not yet implemented" in (result.error_message or "").lower()


def test_service_skips_disabled_channels(tmp_path: Path) -> None:
    prefs_path = tmp_path / "prefs.json"
    svc = NotificationService(preferences_path=prefs_path)

    # All channels disabled by default
    prefs = default_notification_preferences()
    svc.save_preferences(prefs)

    notification = Notification(
        notification_type=NotificationType.JOB_STARTED.value,
        title="Test",
        message="test",
    )
    results = svc.send(notification)
    assert len(results) == 0  # all channels disabled, nothing sent


def test_notification_hook_factory(tmp_path: Path) -> None:
    svc = NotificationService(preferences_path=tmp_path / "prefs.json")
    hook = svc.create_notification_hook()
    # Should not raise even with no channels configured
    hook("job_started", "Test", "test message", {})


def test_service_send_test_no_contacts(tmp_path: Path) -> None:
    svc = NotificationService(preferences_path=tmp_path / "prefs.json")
    result = svc.send_test("email")
    assert result.success is False
    assert "no contacts" in (result.error_message or "").lower()
