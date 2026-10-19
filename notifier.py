import smtplib
from email.message import EmailMessage

import requests

import config

TELEGRAM_MAX_LEN = 4000


def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    for start in range(0, len(text), TELEGRAM_MAX_LEN):
        resp = requests.post(url, data={"chat_id": config.TELEGRAM_CHAT_ID, "text": text[start:start + TELEGRAM_MAX_LEN]}, timeout=30)
        resp.raise_for_status()


def send_email(subject: str, text: str):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.SMTP_USER
    msg["To"] = config.EMAIL_TO
    msg.set_content(text)
    with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
        smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(msg)


def send_github_issue(subject: str, text: str):
    mention = f"@{config.GITHUB_NOTIFY_USER}\n\n" if config.GITHUB_NOTIFY_USER else ""
    resp = requests.post(
        f"https://api.github.com/repos/{config.GITHUB_REPOSITORY}/issues",
        headers={"Authorization": f"Bearer {config.GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
        json={"title": subject, "body": f"{mention}```text\n{text}\n```"},
        timeout=30,
    )
    resp.raise_for_status()


def send_notifications(subject: str, text: str) -> list[str]:
    """Send the report on every configured channel. Returns the channels that failed."""
    channels = []
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        channels.append(("Telegram", lambda: send_telegram(f"{subject}\n\n{text}")))
    if config.SMTP_USER and config.SMTP_PASSWORD and config.EMAIL_TO:
        channels.append(("Email", lambda: send_email(subject, text)))

    if config.GITHUB_TOKEN and config.GITHUB_REPOSITORY:
        channels.append(("GitHub issue", lambda: send_github_issue(subject, text)))

    if not channels:
        print("No notification channel configured; report printed only.")
        return []

    failed = []
    for name, send in channels:
        try:
            send()
            print(f"Sent report via {name}.")
        except Exception as e:
            print(f"Failed to send report via {name}: {e}")
            failed.append(name)
    return failed
