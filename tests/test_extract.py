"""lib.extract の単体テスト（HF/Civitai/非モデル投稿のサンプル）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.extract import extract_model_links, is_model_post, parse_civitai_url, parse_huggingface_url


def test_hf_repo_url():
    link = parse_huggingface_url("https://huggingface.co/black-forest-labs/FLUX.1-dev")
    assert link is not None
    assert link.org == "black-forest-labs"
    assert link.repo == "FLUX.1-dev"
    assert link.is_direct_file is False


def test_hf_resolve_direct_file_url():
    link = parse_huggingface_url(
        "https://huggingface.co/city96/FLUX.1-dev-gguf/resolve/main/flux1-dev-Q4_K_S.gguf"
    )
    assert link is not None
    assert link.is_direct_file is True
    assert link.path == "flux1-dev-Q4_K_S.gguf"


def test_hf_blob_url_is_not_direct_file():
    link = parse_huggingface_url(
        "https://huggingface.co/city96/FLUX.1-dev-gguf/blob/main/flux1-dev-Q4_K_S.gguf"
    )
    assert link is not None
    assert link.is_direct_file is False


def test_civitai_model_url():
    link = parse_civitai_url("https://civitai.com/models/12345/some-cool-lora")
    assert link is not None
    assert link.model_id == "12345"


def test_civitai_model_url_with_version():
    link = parse_civitai_url("https://civitai.com/models/12345?modelVersionId=6789")
    assert link is not None
    assert link.model_id == "12345"
    assert link.version_id == "6789"


def test_non_model_url_returns_none():
    assert parse_huggingface_url("https://example.com/foo") is None
    assert parse_civitai_url("https://example.com/foo") is None


def test_extract_model_links_from_tweet_urls():
    urls = [
        "https://x.com/i/status/123",
        "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0",
    ]
    links = extract_model_links(urls)
    assert len(links) == 1
    assert links[0].kind == "huggingface"


def test_non_model_post_is_skipped():
    urls = ["https://example.com/blog-post", "https://youtube.com/watch?v=abc"]
    assert is_model_post(urls) is False
    assert extract_model_links(urls) == []


def test_civitai_post_is_model_post():
    urls = ["https://civitai.com/models/999"]
    assert is_model_post(urls) is True
