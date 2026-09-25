"""lib.name_search の単体テスト（HF APIはモック・実ネットワークアクセスなし）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.name_search import extract_name_candidates, find_model_from_text


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_extract_candidate_from_possessive_pattern_with_emoji_and_newline():
    text = "Kijai's \U0001F603\nMinimax_h3_ref2va_pruned_w6a8_g32\n\nits experimental"
    candidates = extract_name_candidates(text)
    assert len(candidates) == 1
    assert candidates[0].name == "Minimax_h3_ref2va_pruned_w6a8_g32"
    assert candidates[0].author == "Kijai"


def test_extract_candidate_returns_empty_for_unrelated_post():
    text = "私は普段、オープンウェイトのLocalLLMモデルを改造して…僕が作ったBonza"
    # 主語の後の固有名詞は所有格パターンにもorg/repoパターンにも合致しないため候補ゼロでよい。
    assert extract_name_candidates(text) == []


def test_extract_candidate_zero_for_irrelevant_post():
    text = "こんにちは、今日はいい天気ですね。散歩に行きます。"
    assert extract_name_candidates(text) == []


def test_find_model_from_text_confirms_via_repo_name_match(monkeypatch):
    text = "Kijai's \U0001F603\nMinimax_h3_ref2va_pruned_w6a8_g32\n\nits experimental"

    def fake_get(url, params=None, timeout=None):
        assert url.endswith("/api/models")
        assert params["author"] == "Kijai"
        return FakeResponse([
            {"id": "Kijai/Minimax_h3_ref2va_pruned_w6a8_g32"},
        ])

    result = find_model_from_text(text, http_get=fake_get)
    assert result["status"] == "confirmed"
    assert result["repo_id"] == "Kijai/Minimax_h3_ref2va_pruned_w6a8_g32"


def test_find_model_from_text_confirms_via_sibling_filename_match():
    text = "Kijai's \U0001F603\nMinimax_h3_ref2va_pruned_w6a8_g32\n\nits experimental"

    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        if url.endswith("/api/models"):
            # リポジトリ名自体は一致しないが、中に該当ファイルがある想定
            return FakeResponse([{"id": "Kijai/wan-models-pack"}])
        return FakeResponse({
            "siblings": [
                {"rfilename": "Minimax_h3_ref2va_pruned_w6a8_g32.safetensors"},
            ]
        })

    result = find_model_from_text(text, http_get=fake_get)
    assert result["status"] == "confirmed"
    assert result["repo_id"] == "Kijai/wan-models-pack"
    assert calls["n"] >= 2


def test_find_model_from_text_unconfirmed_when_no_good_hf_match():
    text = "Kijai's \U0001F603\nMinimax_h3_ref2va_pruned_w6a8_g32\n\nits experimental"

    def fake_get(url, params=None, timeout=None):
        if url.endswith("/api/models"):
            return FakeResponse([{"id": "someoneelse/totally-different-thing"}])
        return FakeResponse({"siblings": [{"rfilename": "unrelated.safetensors"}]})

    result = find_model_from_text(text, http_get=fake_get)
    assert result["status"] == "unconfirmed"
    assert result["candidate"] == "Minimax_h3_ref2va_pruned_w6a8_g32"


def test_find_model_from_text_returns_none_when_no_candidates():
    text = "こんにちは、今日はいい天気ですね。散歩に行きます。"

    def fake_get(url, params=None, timeout=None):
        raise AssertionError("候補が無ければHTTPは呼ばれないはず")

    assert find_model_from_text(text, http_get=fake_get) is None


def test_find_model_from_text_not_confirmed_for_ambiguous_bonza_post():
    text = "私は普段、オープンウェイトのLocalLLMモデルを改造して…僕が作ったBonza"

    def fake_get(url, params=None, timeout=None):
        raise AssertionError("候補が無ければHTTPは呼ばれないはず")

    # 候補抽出自体がゼロになるため、確定はもちろん未確定にもならずNoneでよい。
    assert find_model_from_text(text, http_get=fake_get) is None
