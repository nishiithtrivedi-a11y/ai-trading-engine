"""
Email notification channel adapter.

Uses SMTP to send both concise alert emails and richer digest-format emails.
Credentials are read exclusively from environment variables — never from
UI input or logs.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from src.automation.notification.channels.base import (
    BaseNotificationChannel,
    NotificationResult,
)
from src.automation.notification.models import Notification


class EmailChannel(BaseNotificationChannel):
    """SMTP-based email notification channel."""

    @property
    def channel_type(self) -> str:
        return "email"

    def send(
        self,
        notification: Notification,
        target: str,
        **kwargs: Any,
    ) -> NotificationResult:
        """Send an email notification.

        SMTP configuration is read from environment variables:
        - NOTIFICATION_SMTP_HOST
        - NOTIFICATION_SMTP_PORT
        - NOTIFICATION_SMTP_USER
        - NOTIFICATION_SMTP_PASSWORD
        - NOTIFICATION_SMTP_FROM
        - NOTIFICATION_SMTP_USE_TLS (default: true)
        """
        host = os.environ.get("NOTIFICATION_SMTP_HOST", "")
        port_str = os.environ.get("NOTIFICATION_SMTP_PORT", "587")
        user = os.environ.get("NOTIFICATION_SMTP_USER", "")
        password = os.environ.get("NOTIFICATION_SMTP_PASSWORD", "")
        from_addr = os.environ.get("NOTIFICATION_SMTP_FROM", user)
        use_tls = os.environ.get("NOTIFICATION_SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

        if not host:
            return NotificationResult(
                success=False,
                channel=self.channel_type,
                error_message="SMTP host not configured (set NOTIFICATION_SMTP_HOST env var).",
            )

        if not target or "@" not in target:
            return NotificationResult(
                success=False,
                channel=self.channel_type,
                error_message=f"Invalid email target: {target}",
            )

        try:
            port = int(port_str)
        except ValueError:
            port = 587

        # Build email
        is_digest = kwargs.get("digest_mode", False)
        msg = self._build_message(notification, from_addr, target, is_digest)

        try:
            if use_tls:
                server = smtplib.SMTP(host, port, timeout=30)
                server.ehlo()
                server.starttls()
            else:
                server = smtplib.SMTP(host, port, timeout=30)
                server.ehlo()

            if user and password:
                server.login(user, password)

            server.sendmail(from_addr, [target], msg.as_string())
            server.quit()

            return NotificationResult(
                success=True,
                channel=self.channel_type,
                metadata={"to": target, "subject": notification.title},
            )
        except Exception as exc:  # noqa: BLE001
            return NotificationResult(
                success=False,
                channel=self.channel_type,
                error_message=f"SMTP send failed: {exc}",
            )

    def _build_message(
        self,
        notification: Notification,
        from_addr: str,
        to_addr: str,
        digest_mode: bool,
    ) -> MIMEMultipart:
        severity_prefix = f"[{notification.severity.upper()}] " if notification.severity != "info" else ""
        subject = f"{severity_prefix}Trading Engine: {notification.title}"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr

        # Plain text
        text_body = self._format_text(notification, digest_mode)
        msg.attach(MIMEText(text_body, "plain", "utf-8"))

        # HTML
        html_body = self._format_html(notification, digest_mode)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        return msg

    @staticmethod
    def _format_text(notification: Notification, digest_mode: bool) -> str:
        lines = [
            f"AI Trading Engine — {notification.title}",
            f"Type: {notification.notification_type}",
            f"Severity: {notification.severity}",
            f"Time: {notification.timestamp}",
            "",
            notification.message,
        ]
        if notification.artifact_refs:
            lines.append("")
            lines.append("Artifacts:")
            for ref in notification.artifact_refs:
                lines.append(f"  - {ref}")
        if notification.metadata:
            lines.append("")
            lines.append("Details:")
            for key, val in notification.metadata.items():
                lines.append(f"  {key}: {val}")
        return "\n".join(lines)

    @staticmethod
    def _format_html(notification: Notification, digest_mode: bool) -> str:
        severity_color = {
            "info": "#3b82f6",
            "warning": "#f59e0b",
            "error": "#ef4444",
            "signal": "#8b5cf6",
        }.get(notification.severity, "#6b7280")

        artifacts_html = ""
        if notification.artifact_refs:
            items = "".join(f"<li>{ref}</li>" for ref in notification.artifact_refs)
            artifacts_html = f"<h4>Artifacts</h4><ul>{items}</ul>"

        metadata_html = ""
        if notification.metadata:
            rows = "".join(
                f"<tr><td style='padding:4px 8px;font-weight:600'>{k}</td>"
                f"<td style='padding:4px 8px'>{v}</td></tr>"
                for k, v in notification.metadata.items()
            )
            metadata_html = f"<h4>Details</h4><table>{rows}</table>"

        return f"""
        <div style="font-family:system-ui,sans-serif;max-width:600px;margin:0 auto">
            <div style="background:{severity_color};color:white;padding:16px 20px;border-radius:8px 8px 0 0">
                <h2 style="margin:0;font-size:18px">{notification.title}</h2>
                <div style="opacity:0.8;font-size:12px;margin-top:4px">
                    {notification.notification_type} | {notification.severity.upper()} | {notification.timestamp}
                </div>
            </div>
            <div style="background:#f8f9fa;padding:20px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px">
                <p style="margin:0 0 16px 0">{notification.message}</p>
                {artifacts_html}
                {metadata_html}
                <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0">
                <div style="font-size:11px;color:#9ca3af">
                    AI Trading Command Center — Automated Notification (Execution Disabled)
                </div>
            </div>
        </div>
        """
