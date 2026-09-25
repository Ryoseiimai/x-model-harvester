"""Drive上のREADME.md（取得済みモデル一覧）を更新する。"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .paths import DRIVE_README_PATH

TABLE_HEADER = "| モデル名 | 種類 | サイズ | ライセンス | 元投稿URL | 元モデルURL | 取得日 |\n|---|---|---|---|---|---|---|\n"


def _human_size(size_bytes: int | None) -> str:
    if not size_bytes:
        return "-"
    gb = size_bytes / (1024 ** 3)
    if gb >= 0.1:
        return f"{gb:.2f}GB"
    mb = size_bytes / (1024 ** 2)
    return f"{mb:.1f}MB"


def build_row(entry: dict) -> str:
    return (
        f"| {entry.get('filename', '-')} "
        f"| {entry.get('model_kind', '-')} "
        f"| {_human_size(entry.get('size'))} "
        f"| {entry.get('license', '要確認')} "
        f"| {entry.get('tweet_url', '-')} "
        f"| {entry.get('model_url', '-')} "
        f"| {entry.get('fetched_at', '-')} |\n"
    )


UNCONFIRMED_HEADER = "\n## 未確定（リンクなし・モデル名候補のみ。要目視確認）\n\n"


def fetch_current_readme() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "README.md"
        result = subprocess.run(
            ["rclone", "copyto", DRIVE_README_PATH, str(tmp_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not tmp_path.exists():
            return f"# ComfyUIモデル倉庫\n\nX ブックマーク自動収穫で貯まったモデル一覧。\n\n{TABLE_HEADER}"
        return tmp_path.read_text(encoding="utf-8")


def _write_readme(content: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "README.md"
        tmp_path.write_text(content, encoding="utf-8")
        result = subprocess.run(
            ["rclone", "copyto", str(tmp_path), DRIVE_README_PATH],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"README更新のDrive書き込みに失敗: {result.stderr[:500]}")


def append_entries(entries: list[dict]) -> None:
    """新規取得分を表に追記してDriveへ書き戻す。"""
    if not entries:
        return
    current = fetch_current_readme()
    rows = "".join(build_row(e) for e in entries)
    updated = current.rstrip("\n") + "\n" + rows
    _write_readme(updated)


def build_unconfirmed_line(entry: dict) -> str:
    hits = ", ".join(h for h in entry.get("top_hits", []) or []) or "HF検索結果なし"
    return f"- 候補あり・未確定: {entry.get('candidate', '-')} → {hits} （元投稿: {entry.get('tweet_url', '-')}）\n"


def append_unconfirmed_entries(entries: list[dict]) -> None:
    """リンクなしでモデル名候補は見つかったが確証が持てなかった投稿を「未確定」節に追記する。"""
    if not entries:
        return
    current = fetch_current_readme()
    lines = "".join(build_unconfirmed_line(e) for e in entries)
    if "## 未確定" in current:
        updated = current.rstrip("\n") + "\n" + lines
    else:
        updated = current.rstrip("\n") + "\n" + UNCONFIRMED_HEADER + lines
    _write_readme(updated)
