#!/usr/bin/env python3
"""Xブックマーク→モデルファイル自動収穫の本体。

DRY_RUN=1 のときは実際のブックマーク取得→抽出結果の表示までを行い、
ダウンロード・アップロード・状態書き込み・通知は一切しない。
"""
from __future__ import annotations

import datetime
import sys
import tempfile
from pathlib import Path

from lib import civitai_client, extract, fetch_bookmarks, hf_client, license, name_search, notify, readme_update, state
from lib.paths import DRY_RUN, MAX_RETRY_COUNT


def process_tweet(tweet: dict, st: dict) -> dict | None:
    """1件のツイートを処理し、新規取得できたらエントリ情報を返す（未取得ならNone）。

    ダウンロードまで確定した場合は通常のエントリdictを、
    リンクなし投稿から名前候補は見つかったが確証が持てなかった場合は
    `{"_unconfirmed": True, ...}` を返す（呼び出し側でREADMEの別節に振り分ける）。
    """
    tweet_id = tweet["id"]
    links = extract.extract_model_links(tweet["urls"])

    if not links:
        guess = name_search.find_model_from_text(tweet.get("text", ""))
        if guess is None:
            st["items"][tweet_id] = {"status": "skip", "reason": "モデル系リンクなし"}
            st["processed_ids"].append(tweet_id)
            return None

        if guess["status"] == "unconfirmed":
            st["items"][tweet_id] = {
                "status": "unconfirmed",
                "candidate": guess["candidate"],
                "top_hits": guess.get("top_hits", []),
            }
            st["processed_ids"].append(tweet_id)
            return {
                "_unconfirmed": True,
                "candidate": guess["candidate"],
                "top_hits": guess.get("top_hits", []),
                "tweet_url": tweet["url"],
            }

        # confirmed: HF検索で確定した repo_id をリンクとして扱い、以降は通常のHF処理に合流する
        org, repo = guess["repo_id"].split("/", 1)
        links = [
            extract.ExtractedLink(
                kind="huggingface",
                url=f"https://huggingface.co/{guess['repo_id']}",
                parsed=extract.HFLink(org=org, repo=repo, is_direct_file=False),
            )
        ]

    link = links[0]  # 1投稿1モデル想定。複数あれば先頭を採用。
    try:
        if link.kind == "huggingface":
            info = hf_client.resolve_hf_file(link.parsed)
            model_kind = hf_client.guess_model_kind(info["filename"])
            commercial_use = license.resolve_hf_license(link.parsed.repo_id)
            headers = None
        else:
            info = civitai_client.resolve_civitai_file(link.parsed)
            model_kind = _civitai_type_to_kind(info.get("model_type", ""))
            commercial_use = license.classify_civitai_commercial_use(info.get("allow_commercial_use"))
            headers = None
    except (hf_client.HFResolveError, civitai_client.CivitaiResolveError) as exc:
        st["items"][tweet_id] = {"status": "failed", "reason": str(exc), "retry_count": 0}
        st["processed_ids"].append(tweet_id)
        return None

    with tempfile.TemporaryDirectory() as tmp:
        from lib.downloader import download_and_upload

        result = download_and_upload(
            url=info["url"],
            filename=info["filename"],
            model_kind=model_kind,
            work_dir=Path(tmp),
            headers=headers,
        )

    st["items"][tweet_id] = {
        "status": "done",
        "drive_path": result["drive_path"],
        "size": result["size"],
    }
    st["processed_ids"].append(tweet_id)

    return {
        "filename": info["filename"],
        "model_kind": model_kind,
        "size": result["size"],
        "commercial_use": commercial_use["category"],
        "commercial_use_basis": commercial_use.get("basis", "-"),
        "tweet_url": tweet["url"],
        "model_url": link.url,
        "fetched_at": datetime.date.today().isoformat(),
    }


def _civitai_type_to_kind(civitai_type: str) -> str:
    mapping = {
        "Checkpoint": "checkpoints",
        "LORA": "loras",
        "LoCon": "loras",
        "TextualInversion": "other",
        "VAE": "vae",
        "Controlnet": "controlnet",
        "Upscaler": "upscale_models",
    }
    return mapping.get(civitai_type, "other")


def retry_failed_items(st: dict) -> None:
    """前回失敗分をMAX_RETRY_COUNTまで再試行する（意図的簡略化: 現状は再取得ロジックを
    次回のfetch対象化までに留め、失敗理由の記録のみ維持する。フルの自動再取得が要るときは
    ここにtweetの再取得＋process_tweet相当の呼び出しを足す）。
    """
    for tweet_id, item in st["items"].items():
        if item.get("status") == "failed" and item.get("retry_count", 0) < MAX_RETRY_COUNT:
            item["retry_count"] = item.get("retry_count", 0) + 1


def main() -> int:
    tweets = fetch_bookmarks.fetch_recent_bookmarks()

    if DRY_RUN:
        print(f"[DRY_RUN] 取得ツイート数: {len(tweets)}")
        for tweet in tweets:
            links = extract.extract_model_links(tweet["urls"])
            if not links:
                print(f"  - {tweet['id']} skip（モデル系リンクなし）: {tweet['text'][:60]}")
                continue
            for link in links:
                print(f"  - {tweet['id']} {link.kind}: {link.url}")
        return 0

    st = state.load_state()
    processed_ids = set(st["processed_ids"])
    new_entries = []
    new_unconfirmed = []

    for tweet in tweets:
        if tweet["id"] in processed_ids:
            continue
        entry = process_tweet(tweet, st)
        if not entry:
            continue
        if entry.get("_unconfirmed"):
            new_unconfirmed.append(entry)
        else:
            new_entries.append(entry)

    retry_failed_items(st)
    state.save_state(st)

    if new_entries:
        readme_update.append_entries(new_entries)
        notify.notify_new_models(new_entries)

    if new_unconfirmed:
        readme_update.append_unconfirmed_entries(new_unconfirmed)

    print(f"新規処理: {len(new_entries)}件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
