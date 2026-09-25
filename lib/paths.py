"""定数・置き場所の一元管理。"""
from __future__ import annotations

import os

# X API（ブックマークGET）。project_x_bookmark_triage で実測済みの
# OAuth1.0aをそのまま流用する（詳細はREADMEの「認証方式の判断」参照）。
X_USER_ID = "1372999611242008582"
BOOKMARKS_URL = f"https://api.x.com/2/users/{X_USER_ID}/bookmarks"

# 直近分だけ取得（課金抑制・既処理IDで打ち切り）
FETCH_PAGES = 1
FETCH_MAX_RESULTS = 30

# rclone remote（個人Google Drive）
DRIVE_REMOTE = "ryosei_google_drive"
DRIVE_BASE_DIR = "AI素材/ComfyUIモデル倉庫"
DRIVE_BASE = f"{DRIVE_REMOTE}:{DRIVE_BASE_DIR}"
DRIVE_STATE_PATH = f"{DRIVE_BASE}/.state/harvester.json"
DRIVE_README_PATH = f"{DRIVE_BASE}/README.md"

# 種類フォルダ（ComfyUIのモデルディレクトリ構成に合わせる）
MODEL_KINDS = (
    "checkpoints",
    "diffusion_models",
    "text_encoders",
    "vae",
    "loras",
    "upscale_models",
    "controlnet",
    "other",
)

# ダウンロード制約
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024 * 1024  # 25GB
MAX_RETRY_COUNT = 3

DRY_RUN = os.environ.get("DRY_RUN") == "1"
