"""
Telegram notification channel adapter.

Uses the Telegram Bot API to send concise alert messages.
Bot token is read exclusively from environment variables — never from
UI input or logs.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Any

from src.automation.notification.channels.base import (
    BaseNotificationChannel,
    NotificationResult,
)
from src.automation.notification.models import Notification


_SEVERITY_EMOJI = {
    "info": "ℹ️",
    "warning": "⚠️",
    "error": "🔴",
    "signal": "📡",
}


class TelegramChannel(BaseNotificationChannel):
    """Telegram Bot API notification channel."""

    @property
    def channel_type(self) -> str:
        return "telegram"

    def send(
        self,
        notification: Notification,
        target: str,
        **kwargs: Any,
    ) -> NotificationResult:
        """Send a Telegram message.

        Configuration:
        - NOTIFICATION_TELEGRAM_BOT_TOKEN env var (required)
        - target = chat_id (passed per ContactTarget)
        """
        bot_token = os.environ.get("NOTIFICATION_TELEGRAM_BOT_TOKEN", "")

        if not bot_token:
            return NotificationResult(
                success=False,
                channel=self.channel_type,
                error_message="Telegram bot token not configured (set NOTIFICATION_TELEGRAM_BOT_TOKEN env var).",
            )

        if not target:
            return NotificationResult(
                success=False,
                channel=self.channel_type,
                error_message="Telegram chat_id target is empty.",
            )

        text = self._format_message(notification)

        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = json.dumps({
                "chat_id": target,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result_data = json.loads(resp.read().decode("utf-8"))

            if result_data.get("ok"):
                return NotificationResult(
                    success=True,
                    channel=self.channel_type,
                    metadata={"chat_id": target, "message_id": result_data.get("result", {}).get("message_id")},
                )
            else:
                return NotificationResult(
                    success=False,
                    channel=self.channel_type,
                    error_message=f"Telegram API error: {result_data.get('description', 'unknown')}",
                )

        except urllib.error.URLError as exc:
            return NotificationResult(
                success=False,
                channel=self.channel_type,
                error_message=f"Telegram send failed: {exc}",
            )
        except Exception as exc:  # noqa: BLE001
            return NotificationResult(
                success=False,
                channel=self.channel_type,
                error_message=f"Telegram send error: {exc}",
            )

    @staticmethod
    def _format_message(notification: Notification) -> str:
        emoji = _SEVERITY_EMOJI.get(notification.severity, "ℹ️")
        lines = [
            f"{emoji} <b>{notification.title}</b>",
            "",
            notification.message,
            "",
            f"⏱ {notification.timestamp}",
            f"📋 {notification.notification_type}",
        ]

        if notification.artifact_refs:
            lines.append("")
            lines.append("📎 Artifacts:")
            for ref in notification.artifact_refs[:5]:
                lines.append(f"  • {ref}")

        if notification.metadata:
            lines.append("")
            for key, val in list(notification.metadata.items())[:5]:
                lines.append(f"  {key}: {val}")

        lines.append("")
        lines.append("<i>AI Trading Engine — Execution Disabled</i>")
        return "\n".join(lines)
