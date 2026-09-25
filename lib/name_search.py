"""HF/Civitaiリンクが無い投稿から、モデル名らしき候補を正規表現で拾い、
HuggingFace検索APIで確度の高いものだけ確定する。

意図的簡略化: LLMは使わず正規表現＋文字列一致のみで判定する。誤爆でおかしなファイルを
大量DLする実害の方が大きいため、確信が持てる場合のみ確定採用し、それ以外は
「未確定」としてstate/READMEに残すだけに留める。本格的な曖昧一致・埋め込み検索・
LLM判定を入れるならこのモジュールを差し替える。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import requests

HF_SEARCH_API = "https://huggingface.co/api/models"

# 候補抽出パターン。
# 1) 所有格: "Kijai's ... Minimax_h3_ref2va_pruned_w6a8_g32"（絵文字・改行を挟んでもよい）
_POSSESSIVE_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9_]{1,30})'s\b[^\w]{0,10}([A-Za-z0-9][A-Za-z0-9_\-.]{3,80})",
)
# 2) 拡張子付きファイル名: "xxx.safetensors" / "xxx.gguf"
_FILENAME_RE = re.compile(r"\b[\w][\w\-.]*\.(?:safetensors|gguf)\b", re.IGNORECASE)
# 3) org/repo 形式（HuggingFaceのリポジトリID表記）
_ORG_REPO_RE = re.compile(r"\b([A-Za-z][\w\-.]{1,30})/([A-Za-z0-9][\w\-.]{1,60})\b")
# 4) サイズ・量子化タグ付きモデル名: "xxx-7B" "xxx-GGUF" "xxx-Q4" 等
_TAGGED_MODEL_RE = re.compile(
    r"\b[A-Za-z][\w\-.]*-(?:\d{1,3}B|GGUF|Q4|Q5|Q6|Q8|FP8|FP16)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class NameCandidate:
    name: str
    author: str | None = None


def extract_name_candidates(text: str) -> list[NameCandidate]:
    """本文からモデル名っぽい候補を抽出する（重複除去・出現順維持）。"""
    seen: set[str] = set()
    candidates: list[NameCandidate] = []

    def add(name: str, author: str | None = None) -> None:
        key = name.lower()
        if key in seen:
            return
        seen.add(key)
        candidates.append(NameCandidate(name=name, author=author))

    for m in _POSSESSIVE_RE.finditer(text):
        add(m.group(2), author=m.group(1))

    for m in _FILENAME_RE.finditer(text):
        add(m.group(0))

    for m in _ORG_REPO_RE.finditer(text):
        org, repo = m.group(1), m.group(2)
        if org.isdigit() or repo.isdigit():
            continue  # 日付表記(09/25)等の除外
        if len(org) < 2 or len(repo) < 2:
            continue
        add(f"{org}/{repo}")

    for m in _TAGGED_MODEL_RE.finditer(text):
        add(m.group(0))

    return candidates


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def search_candidate_on_hf(candidate: NameCandidate, http_get=requests.get) -> dict:
    """HF検索APIで候補を検証する。

    戻り値:
      {"status": "confirmed", "repo_id": "...", "candidate": name}
      {"status": "unconfirmed", "candidate": name, "top_hits": [...]}
    """
    params: dict = {"search": candidate.name, "limit": 5}
    if candidate.author:
        params["author"] = candidate.author

    resp = http_get(HF_SEARCH_API, params=params, timeout=15)
    resp.raise_for_status()
    results = resp.json() or []

    target = _normalize(candidate.name)

    # リポジトリ名で一致するか
    for r in results:
        repo_id = r.get("id", "")
        repo_name = repo_id.split("/")[-1]
        norm_repo = _normalize(repo_name)
        if norm_repo and target and (target == norm_repo or target in norm_repo or norm_repo in target):
            return {"status": "confirmed", "repo_id": repo_id, "candidate": candidate.name}

    # リポジトリ名で一致しない場合、上位候補のファイル名一致を見る
    # （Kijaiの個人配布のようにリポジトリ内の特定ファイル単位で名前が付くケース）
    for r in results[:3]:
        repo_id = r.get("id", "")
        if not repo_id:
            continue
        try:
            detail = http_get(f"{HF_SEARCH_API}/{repo_id}", timeout=15)
            detail.raise_for_status()
        except requests.RequestException:
            continue
        siblings = (detail.json() or {}).get("siblings", []) or []
        for s in siblings:
            fname = s.get("rfilename", "")
            base = fname.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            norm_file = _normalize(base)
            if norm_file and target and (target == norm_file or target in norm_file or norm_file in target):
                return {"status": "confirmed", "repo_id": repo_id, "candidate": candidate.name}

    top_hits = [r.get("id", "") for r in results[:3] if r.get("id")]
    return {"status": "unconfirmed", "candidate": candidate.name, "top_hits": top_hits}


def find_model_from_text(text: str, http_get=requests.get) -> dict | None:
    """本文からモデル候補を抽出し、HF検索で検証する。

    候補が1つも無ければ None（＝通常のリンクなしskip）。
    確定できた候補があればそれを返す。どれも確定しなければ最初の候補の未確定情報を返す。
    """
    candidates = extract_name_candidates(text)
    if not candidates:
        return None

    first_unconfirmed: dict | None = None
    for candidate in candidates:
        result = search_candidate_on_hf(candidate, http_get=http_get)
        if result["status"] == "confirmed":
            return result
        if first_unconfirmed is None:
            first_unconfirmed = result
    return first_unconfirmed
