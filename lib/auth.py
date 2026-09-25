"""X API (OAuth1) 認証。

~/dev/2026-08-10-x-bookmark-triage/lib/auth.py と同じ流儀。
環境変数を最優先で読む（GitHub Actions の Secrets 注入を想定）。
ローカル動作確認時は ~/.x_api_tokens.zsh からも読める。
資格情報はコード・ログのどちらにも直接出力しない。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

TOKENS_FILE = Path("~/.x_api_tokens.zsh").expanduser()

REQUIRED_KEYS = (
    "X_CONSUMER_KEY",
    "X_CONSUMER_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
)


def _load_dotenv_style_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^export\s+", "", line)
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def load_credentials() -> dict[str, str]:
    file_env = _load_dotenv_style_file(TOKENS_FILE)
    creds = {key: os.environ.get(key) or file_env.get(key) for key in REQUIRED_KEYS}
    missing = [key for key, value in creds.items() if not value]
    if missing:
        raise SystemExit(
            f"X API の資格情報が不足しています: {missing} "
            f"(環境変数 or {TOKENS_FILE} を確認してください)"
        )
    return creds


def oauth_session():
    """認証済みの OAuth1Session を返す。"""
    from requests_oauthlib import OAuth1Session

    creds = load_credentials()
    return OAuth1Session(
        creds["X_CONSUMER_KEY"],
        client_secret=creds["X_CONSUMER_SECRET"],
        resource_owner_key=creds["X_ACCESS_TOKEN"],
        resource_owner_secret=creds["X_ACCESS_TOKEN_SECRET"],
    )
