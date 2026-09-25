"""新規取得があった回だけ本人へメール通知する（任意機能）。

既存の通知経路（Slack/Mail.app AppleScript等）はいずれもmacOSローカル前提で
GitHub Actions(Ubuntu)から使えないため流用不可。Secrets `GMAIL_ADDRESS` /
`GMAIL_APP_PASSWORD`（Googleアカウントの「アプリパスワード」）がある場合のみ
smtplibでGmail送信する。無ければ通知はスキップし、README側の一覧確認に委ねる
（意図的な簡略化: 本番のGmail通知基盤との統合は別途）。
"""
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
NOTIFY_TO = "kaeru3160@gmail.com"


def notify_new_models(entries: list[dict]) -> bool:
    """送信したらTrue、Secrets未設定でスキップしたらFalseを返す。"""
    if not entries:
        return False

    address = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not address or not app_password:
        return False

    lines = [f"- {e.get('filename', '?')} ({e.get('model_kind', '?')}) 元投稿: {e.get('tweet_url', '-')}" for e in entries]
    body = "新規取得モデル:\n\n" + "\n".join(lines)

    msg = MIMEText(body)
    msg["Subject"] = f"【モデル倉庫】{len(entries)}件追加"
    msg["From"] = address
    msg["To"] = NOTIFY_TO

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(address, app_password)
        server.sendmail(address, [NOTIFY_TO], msg.as_string())
    return True
