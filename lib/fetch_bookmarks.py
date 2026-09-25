"""Xブックマークを取得し正規化する（x-bookmark-triage/fetch.py の縮小移植）。

このプロジェクト専用に持たせている理由: 元プロジェクトは分類・優先キュー用途で
フィールド構成が異なり、依存させると片方の変更がもう片方を壊すため（DRY原則より
運用分離を優先）。
"""
from __future__ import annotations

import sys
import time
from typing import Any

import requests

from . import auth, paths

HTTP_TOO_MANY_REQUESTS = 429
BODY_PREVIEW_LEN = 200
MAX_CONNECT_RETRIES = 3
BACKOFF_BASE_SEC = 2

TWEET_FIELDS = "created_at,entities,text"
USER_FIELDS = "username,name"
EXPANSIONS = "author_id"


def get_with_retry(session, params: dict[str, Any]):
    for attempt in range(1, MAX_CONNECT_RETRIES + 1):
        try:
            return session.get(paths.BOOKMARKS_URL, params=params, timeout=30)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            if attempt == MAX_CONNECT_RETRIES:
                raise
            wait_sec = BACKOFF_BASE_SEC * (2 ** (attempt - 1))
            print(f"リトライ {attempt}/{MAX_CONNECT_RETRIES}: {exc}", file=sys.stderr)
            time.sleep(wait_sec)


def fetch_page(session) -> dict[str, Any]:
    params = {
        "max_results": paths.FETCH_MAX_RESULTS,
        "tweet.fields": TWEET_FIELDS,
        "expansions": EXPANSIONS,
        "user.fields": USER_FIELDS,
    }
    resp = get_with_retry(session, params)
    if resp.status_code == HTTP_TOO_MANY_REQUESTS:
        print(f"X API レート制限(429): {resp.text[:BODY_PREVIEW_LEN]}", file=sys.stderr)
        sys.exit(3)
    if resp.status_code != 200:
        print(
            f"X API エラー status={resp.status_code} body={resp.text[:BODY_PREVIEW_LEN]}",
            file=sys.stderr,
        )
        sys.exit(2)
    return resp.json()


def normalize_item(item: dict[str, Any], users_by_id: dict[str, dict[str, str]]) -> dict[str, Any]:
    tweet_id = item["id"]
    author_id = item.get("author_id", "")
    author_info = users_by_id.get(author_id, {})

    entities = item.get("entities", {}) or {}
    urls: list[str] = []
    for url_entity in entities.get("urls", []) or []:
        expanded = url_entity.get("expanded_url", "")
        if not expanded:
            continue
        if "x.com/" in expanded or "twitter.com/" in expanded:
            continue
        urls.append(expanded)

    return {
        "id": tweet_id,
        "url": f"https://x.com/i/status/{tweet_id}",
        "author": author_info.get("username", author_id),
        "created_at": item.get("created_at", ""),
        "text": item.get("text", ""),
        "urls": urls,
    }


def fetch_recent_bookmarks() -> list[dict[str, Any]]:
    """直近1ページ分のブックマークを正規化して返す（課金抑制のため常に1ページ）。"""
    session = auth.oauth_session()
    payload = fetch_page(session)
    data = payload.get("data", []) or []
    includes_users = payload.get("includes", {}).get("users", []) or []
    users_by_id = {u["id"]: u for u in includes_users}
    return [normalize_item(raw, users_by_id) for raw in data]
