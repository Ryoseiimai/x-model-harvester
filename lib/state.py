"""処理済みID・取得履歴の状態を Google Drive 上の JSON で管理する。

repo にコミットしない・public repoに秘密を残さないため、rclone経由でDrive上の
`.state/harvester.json` を直接読み書きする（GitHub Actionsランナーはジョブ終了で
使い捨てになるためローカル永続化ができない）。

DRY_RUN時はDriveへ一切アクセスせず、空の状態を返す（読み取り専用の抽出結果確認のため）。
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .paths import DRIVE_STATE_PATH, DRY_RUN

DEFAULT_STATE: dict[str, Any] = {
    "processed_ids": [],  # 処理済みツイートID（成功・skip・要ログイン等すべて含む）
    "items": {},          # "<tweet_id>": {status, reason, model_url, drive_path, retry_count, ...}
}


def load_state() -> dict[str, Any]:
    if DRY_RUN:
        return json.loads(json.dumps(DEFAULT_STATE))

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "harvester.json"
        result = subprocess.run(
            ["rclone", "copyto", DRIVE_STATE_PATH, str(tmp_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not tmp_path.exists():
            # 初回実行等でファイルが無い場合は空状態から始める
            return json.loads(json.dumps(DEFAULT_STATE))
        return json.loads(tmp_path.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    if DRY_RUN:
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "harvester.json"
        tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = subprocess.run(
            ["rclone", "copyto", str(tmp_path), DRIVE_STATE_PATH],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"状態ファイルのDrive書き込みに失敗: {result.stderr[:500]}")
