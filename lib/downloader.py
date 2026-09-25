"""モデルファイルのDL→Driveアップロード→ローカル削除。

ランナーのディスク容量を圧迫しないよう、ダウンロードとアップロードを
1件ずつ直列に行い、成功・失敗にかかわらずローカルファイルを都度削除する。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import requests

from .paths import DRIVE_BASE, MAX_FILE_SIZE_BYTES

DOWNLOAD_CHUNK_SIZE = 8 * 1024 * 1024  # 8MB


class DownloadError(Exception):
    pass


def download_file(url: str, dest_path: Path, headers: dict | None = None) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    with requests.get(url, headers=headers or {}, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        with dest_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if not chunk:
                    continue
                downloaded += len(chunk)
                if downloaded > MAX_FILE_SIZE_BYTES:
                    raise DownloadError(f"サイズ上限超過（>{MAX_FILE_SIZE_BYTES}バイト）: {url}")
                f.write(chunk)


def upload_to_drive(local_path: Path, model_kind: str) -> str:
    """rclone copytoでDriveへ上げる。戻り値はDrive上のパス。"""
    drive_path = f"{DRIVE_BASE}/{model_kind}/{local_path.name}"
    result = subprocess.run(
        ["rclone", "copyto", str(local_path), drive_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DownloadError(f"Driveアップロード失敗: {result.stderr[:500]}")
    return drive_path


def verify_size(local_path: Path, expected_size: int | None) -> bool:
    if expected_size is None:
        return True
    return local_path.stat().st_size == expected_size


def download_and_upload(url: str, filename: str, model_kind: str, work_dir: Path, headers: dict | None = None) -> dict:
    """1件のDL→アップロード→ローカル削除を行い、結果情報を返す。"""
    local_path = work_dir / filename
    try:
        download_file(url, local_path, headers=headers)
        size = local_path.stat().st_size
        drive_path = upload_to_drive(local_path, model_kind)
        return {"ok": True, "drive_path": drive_path, "size": size}
    finally:
        if local_path.exists():
            local_path.unlink()
