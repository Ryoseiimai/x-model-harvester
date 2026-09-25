"""HuggingFace側のファイル解決（ネットワークアクセスあり）。

方針:
- 個別ファイルURL（/resolve/<rev>/<path>）ならそのまま使う。
- リポジトリURL・blobリンクなら HF API (`/api/models/<repo_id>`) でファイル一覧を取得し、
  .safetensors / .gguf を優先、fp8 > fp16 > 量子化 > その他の順で1つ選ぶ。
  全精度fp32のみの場合は「fp32のみで対象外」として選ばない。
- ゲート付きリポジトリ（401/403）は「要ログイン」として呼び出し側にNoneで伝える。
"""
from __future__ import annotations

import requests

from .extract import HFLink
from .paths import MAX_FILE_SIZE_BYTES

HF_API_BASE = "https://huggingface.co/api/models"
MODEL_FILE_EXTS = (".safetensors", ".gguf")

# 優先度が低いほど先に採用される。fp32のみのファイルは選ばない。
PRECISION_PRIORITY = ("fp8", "int8", "q4", "q5", "q6", "q8", "gguf", "fp16", "bf16")


class HFResolveError(Exception):
    """ゲート付き・存在しない等、取得不能を表す。"""


def _score_filename(name: str) -> tuple[int, str]:
    lower = name.lower()
    if "fp32" in lower or "f32" in lower:
        # fp32単体は基本非採用対象だが、他に候補が無ければ最後の保険として残す
        return (len(PRECISION_PRIORITY) + 1, name)
    for idx, key in enumerate(PRECISION_PRIORITY):
        if key in lower:
            return (idx, name)
    return (len(PRECISION_PRIORITY), name)


def resolve_hf_file(link: HFLink) -> dict:
    """ダウンロード対象ファイルの情報（url, filename, size）を返す。"""
    if link.is_direct_file:
        rev = link.revision or "main"
        url = f"https://huggingface.co/{link.repo_id}/resolve/{rev}/{link.path}"
        return {"url": url, "filename": link.path.rsplit("/", 1)[-1], "size": None}

    resp = requests.get(f"{HF_API_BASE}/{link.repo_id}", timeout=30)
    if resp.status_code in (401, 403):
        raise HFResolveError("要ログイン（ゲート付きリポジトリ）")
    if resp.status_code == 404:
        raise HFResolveError("リポジトリが見つかりません")
    resp.raise_for_status()
    data = resp.json()

    siblings = data.get("siblings", []) or []
    candidates = [
        s["rfilename"]
        for s in siblings
        if s.get("rfilename", "").lower().endswith(MODEL_FILE_EXTS)
    ]
    if not candidates:
        raise HFResolveError("対象拡張子(.safetensors/.gguf)のファイルが見つかりません")

    # fp32のみ除外した候補を優先。fp32しか無ければ最後の保険でそれを使う。
    non_fp32 = [c for c in candidates if "fp32" not in c.lower() and "f32" not in c.lower()]
    pool = non_fp32 or candidates
    best = sorted(pool, key=_score_filename)[0]

    rev = "main"
    url = f"https://huggingface.co/{link.repo_id}/resolve/{rev}/{best}"
    return {"url": url, "filename": best.rsplit("/", 1)[-1], "size": None}


def guess_model_kind(filename: str, tags: list[str] | None = None) -> str:
    """ファイル名・タグからComfyUIの種類フォルダを推定する（フォールバックは other）。"""
    lower = filename.lower()
    tag_text = " ".join(tags or []).lower()
    combined = f"{lower} {tag_text}"

    if "vae" in combined:
        return "vae"
    if "lora" in combined:
        return "loras"
    if "controlnet" in combined or "control_net" in combined:
        return "controlnet"
    if "upscal" in combined or "esrgan" in combined:
        return "upscale_models"
    if "text_encoder" in combined or "clip" in combined or "t5" in combined:
        return "text_encoders"
    if "diffusion" in combined or "unet" in combined:
        return "diffusion_models"
    if "checkpoint" in combined or lower.endswith(".safetensors"):
        return "checkpoints"
    return "other"


def check_size_ok(size_bytes: int | None) -> bool:
    if size_bytes is None:
        return True  # サイズ不明時は後続のDL時にストリームで打ち切る
    return size_bytes <= MAX_FILE_SIZE_BYTES
