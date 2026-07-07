from __future__ import annotations

import json
import smtplib
import syslog
from email.message import EmailMessage
from urllib import request

from .discovery import now


def get_setting(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def notify_failure(conn, job_run_id: int, message: str) -> None:
    for channel in ("email", "webhook", "syslog"):
        status, error = send(conn, channel, message)
        conn.execute(
            """
            INSERT INTO notifications (job_run_id, channel, status, message, error, sent_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_run_id, channel, status, message, error, now()),
        )


def send(conn, channel: str, message: str) -> tuple[str, str]:
    try:
        if channel == "webhook":
            url = get_setting(conn, "notification.webhook_url")
            if not url:
                return "skipped", "notification.webhook_url not configured"
            req = request.Request(
                url,
                data=json.dumps({"text": message}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=5) as resp:
                return "sent", f"HTTP {resp.status}"
        if channel == "email":
            host = get_setting(conn, "notification.smtp_host")
            to_addr = get_setting(conn, "notification.email_to")
            from_addr = get_setting(conn, "notification.email_from") or "sonargrid@localhost"
            if not host or not to_addr:
                return "skipped", "SMTP host or recipient not configured"
            msg = EmailMessage()
            msg["Subject"] = "SonarGrid collection failure"
            msg["From"] = from_addr
            msg["To"] = to_addr
            msg.set_content(message)
            with smtplib.SMTP(host, timeout=5) as smtp:
                smtp.send_message(msg)
            return "sent", ""
        if channel == "syslog":
            syslog.syslog(syslog.LOG_WARNING, message)
            return "sent", ""
        return "skipped", f"unknown channel: {channel}"
    except Exception as exc:  # noqa: BLE001 - visible in notification history
        return "failed", str(exc)
