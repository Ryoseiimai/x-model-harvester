"""Civitai側のファイル解決（ネットワークアクセスあり）。

Secret `CIVITAI_TOKEN` が無い場合は「要鍵」として呼び出し側にNoneで伝える
（意図的な簡略化: 未ログインでもダウンロードできる場合があるが、レート制限や
ゲート付きモデルの扱いが不安定なため、鍵ありの場合だけ処理する方針にした）。
"""
from __future__ import annotations

import os

import requests

from .extract import CivitaiLink

CIVITAI_API_BASE = "https://civitai.com/api/v1"


class CivitaiResolveError(Exception):
    """要鍵・存在しない等、取得不能を表す。"""


def _get_token() -> str | None:
    return os.environ.get("CIVITAI_TOKEN")


def resolve_civitai_file(link: CivitaiLink) -> dict:
    token = _get_token()
    if not token:
        raise CivitaiResolveError("要鍵（CIVITAI_TOKEN未設定）")

    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{CIVITAI_API_BASE}/models/{link.model_id}", headers=headers, timeout=30)
    if resp.status_code == 404:
        raise CivitaiResolveError("モデルが見つかりません")
    resp.raise_for_status()
    data = resp.json()

    versions = data.get("modelVersions", []) or []
    if link.version_id:
        versions = [v for v in versions if str(v.get("id")) == link.version_id] or versions
    if not versions:
        raise CivitaiResolveError("モデルバージョンが見つかりません")

    version = versions[0]  # 最新バージョン（modelVersionsは新しい順で返る）
    files = version.get("files", []) or []
    primary = next((f for f in files if f.get("primary")), files[0] if files else None)
    if not primary:
        raise CivitaiResolveError("ダウンロード対象ファイルが見つかりません")

    return {
        "url": primary.get("downloadUrl"),
        "filename": primary.get("name"),
        "size": int(primary.get("sizeKB", 0) * 1024) if primary.get("sizeKB") else None,
        "model_type": data.get("type", ""),
        "allow_commercial_use": data.get("allowCommercialUse"),
    }
