"""投稿本文＋展開済みURLからHuggingFace/Civitaiのモデルリンクを抽出する。

このモジュールはネットワークアクセスを一切しない（純粋なパース処理）。
単体テストで検証しやすくするため、副作用を持たせていない。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

HF_HOST_RE = re.compile(r"^https?://huggingface\.co/")
CIVITAI_HOST_RE = re.compile(r"^https?://civitai\.com/")

# huggingface.co/<org>/<repo>[/blob|resolve/<rev>/<path...>]
HF_REPO_RE = re.compile(
    r"^https?://huggingface\.co/(?P<org>[^/]+)/(?P<repo>[^/]+)"
    r"(?:/(?P<kind>blob|resolve)/(?P<rev>[^/]+)/(?P<path>.+))?/?$"
)

# civitai.com/models/<id>[/<slug>][?modelVersionId=<vid>]
CIVITAI_MODEL_RE = re.compile(
    r"^https?://civitai\.com/models/(?P<model_id>\d+)(?:/[^?]*)?(?:\?.*modelVersionId=(?P<version_id>\d+))?"
)


@dataclass(frozen=True)
class HFLink:
    org: str
    repo: str
    is_direct_file: bool
    revision: str | None = None
    path: str | None = None

    @property
    def repo_id(self) -> str:
        return f"{self.org}/{self.repo}"


@dataclass(frozen=True)
class CivitaiLink:
    model_id: str
    version_id: str | None = None


def parse_huggingface_url(url: str) -> HFLink | None:
    if not HF_HOST_RE.match(url):
        return None
    m = HF_REPO_RE.match(url)
    if not m:
        return None
    kind = m.group("kind")
    path = m.group("path")
    is_direct_file = kind == "resolve" and bool(path)
    # blob/ はブラウザ表示用リンクでダウンロード直リンクではない。
    # resolve/ はダウンロード直リンク。
    return HFLink(
        org=m.group("org"),
        repo=m.group("repo"),
        is_direct_file=is_direct_file,
        revision=m.group("rev"),
        path=path,
    )


def parse_civitai_url(url: str) -> CivitaiLink | None:
    if not CIVITAI_HOST_RE.match(url):
        return None
    m = CIVITAI_MODEL_RE.match(url)
    if not m:
        return None
    return CivitaiLink(model_id=m.group("model_id"), version_id=m.group("version_id"))


@dataclass(frozen=True)
class ExtractedLink:
    kind: str  # "huggingface" | "civitai"
    url: str
    parsed: HFLink | CivitaiLink


def extract_model_links(urls: list[str]) -> list[ExtractedLink]:
    """展開済みURL一覧からHF/Civitaiのモデルリンクだけを抜き出す。

    モデル系でない投稿（HF/Civitaiリンクが1つもない）は空リストになる。
    呼び出し側はこれをもって「skip」判定する。
    """
    found: list[ExtractedLink] = []
    for url in urls:
        hf = parse_huggingface_url(url)
        if hf:
            found.append(ExtractedLink(kind="huggingface", url=url, parsed=hf))
            continue
        civitai = parse_civitai_url(url)
        if civitai:
            found.append(ExtractedLink(kind="civitai", url=url, parsed=civitai))
    return found


def is_model_post(urls: list[str]) -> bool:
    return len(extract_model_links(urls)) > 0
