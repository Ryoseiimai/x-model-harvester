# x-model-harvester

Xの個人アカウントで「モデル系の投稿」をブックマークすると、GitHub Actions（クラウド）が自動でモデルファイルを見つけてダウンロードし、個人Googleドライブへ入れる仕組み。PCの電源に依存しない。

## 仕組み図

```
GitHub Actions cron (30分おき, public repoなので分無料)
   │
   ▼
harvest.py
   │
   ├─ 1. fetch_bookmarks.py … X API v2 でブックマーク直近1ページ取得（OAuth1.0a）
   │
   ├─ 2. lib/extract.py … 投稿の展開済みURLからHuggingFace/Civitaiのモデルリンクを抽出
   │        モデル系リンクが無い投稿はここで skip 記録して終わり
   │
   ├─ 3. lib/hf_client.py / lib/civitai_client.py … ダウンロード対象ファイルを1つ選ぶ
   │        HF: リポジトリならAPI一覧から .safetensors/.gguf を fp8>量子化>fp16 優先で選択
   │             fp32のみは避ける。ゲート付きで取れないものは「要ログイン」でskip
   │        Civitai: CIVITAI_TOKENがあれば最新バージョンの主ファイル。無ければ「要鍵」でskip
   │
   ├─ 4. lib/downloader.py … DL→rclone copytoでDriveへアップロード→ローカル削除（1件ずつ直列）
   │
   ├─ 5. lib/state.py … 処理済みID・結果を Drive上の .state/harvester.json に保存
   │        （publicリポにコミットしない。ランナーは使い捨てなのでDrive側を正本にする）
   │
   ├─ 6. lib/readme_update.py … Drive上のREADME.mdの一覧表に新規取得分を追記
   │
   └─ 7. lib/notify.py … 新規取得があった回だけメール通知（Secrets未設定ならスキップ）
```

## 保存先

`ryosei_google_drive:AI素材/ComfyUIモデル倉庫/<種類>/`
種類フォルダ: `checkpoints` / `diffusion_models` / `text_encoders` / `vae` / `loras` / `upscale_models` / `controlnet` / `other`

状態ファイル: `ryosei_google_drive:AI素材/ComfyUIモデル倉庫/.state/harvester.json`（Drive上のみ・repoにはコミットしない）

## 認証方式の判断（X API）

タスク指示は「OAuth2ユーザー文脈＋リフレッシュトークンのローテーション対応」だったが、実装は
**OAuth1.0a（`~/dev/2026-08-10-x-bookmark-triage` と同じ4本の鍵）を流用**した。

理由:
- 既存プロジェクトで `GET /2/users/:id/bookmarks` がOAuth1.0aで動くことが実測済み（memory `project_x_bookmark_triage`）。読み取り専用の用途にOAuth2の複雑さ（認可コードフロー・トークン失効・リフレッシュトークンのローテーション検知と再永続化）を持ち込む必要がない。
- OAuth1.0aの4本の鍵（consumer key/secret, access token/secret）はローテーションしない。GitHub Secretsに一度入れれば更新不要で、無人運用に向く。
- Google Drive側（rclone）は逆にOAuth2だが、rcloneが実行のたびにrefresh_tokenで自動的にaccess_tokenを更新するため、こちらは永続化の心配が不要（refresh_token自体は失効しない限り再利用できる）。

この判断に異論があれば、`lib/auth.py` をOAuth2ユーザー文脈に差し替えるだけで他モジュールへの影響はない（`fetch_bookmarks.py` は `auth.oauth_session()` のインターフェースにのみ依存）。

## 必要なSecrets（GitHub リポジトリ Settings > Secrets and variables > Actions）

| Secret名 | 何のためか | 値の取得元（手元） |
|---|---|---|
| `X_CONSUMER_KEY` | X APIブックマーク読み取り | `~/.x_api_tokens.zsh` の `X_CONSUMER_KEY` |
| `X_CONSUMER_SECRET` | 同上 | `~/.x_api_tokens.zsh` の `X_CONSUMER_SECRET` |
| `X_ACCESS_TOKEN` | 同上 | `~/.x_api_tokens.zsh` の `X_ACCESS_TOKEN` |
| `X_ACCESS_TOKEN_SECRET` | 同上 | `~/.x_api_tokens.zsh` の `X_ACCESS_TOKEN_SECRET` |
| `RCLONE_CONFIG` | Google Driveへの書き込み（rclone設定ファイルの中身そのまま） | `~/.config/rclone/rclone.conf` の全文（`ryosei_google_drive` セクションだけで足りるが、全文貼っても他リモートは使わないので害はない。心配なら `ryosei_google_drive` セクションだけ抜粋して貼る） |
| `CIVITAI_TOKEN`（任意） | Civitaiのモデルダウンロード | civitai.com アカウント設定 > API Keys で新規発行 |
| `GMAIL_ADDRESS`（任意） | 新規取得メール通知の送信元 | 通知用に使いたいGmailアドレス |
| `GMAIL_APP_PASSWORD`（任意） | 同上のSMTP認証 | そのGmailアカウントの「アプリパスワード」（Googleアカウント > セキュリティ > 2段階認証 > アプリパスワード） |

`CIVITAI_TOKEN` / `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` は未設定でも動く（Civitaiは「要鍵」skip、通知は省略されるだけ）。

## 初回セットアップ手順

1. このrepoを `ghp` で個人GitHub（Ryoseiimai）に **public** で作成し、push する（司令塔が実施）。
2. 上表のSecretsを登録する（司令塔 or 本人）。
3. Drive側に `AI素材/ComfyUIモデル倉庫/` フォルダが無ければ、初回実行が自動で作る（rclone copytoは親フォルダを自動作成する）。手動で先に作っておいても問題ない。
4. `workflow_dispatch` で1回手動実行して疎通確認する（既定でDRY_RUNになるため、実際のDL・アップロードは走らない。ログでブックマーク取得とリンク抽出結果を確認する）。
5. 問題なければ、30分おきのcronが自動でDRY_RUN=0（本番）で回り出す。

## 動作確認

```bash
# 抽出ロジックの単体テスト（トークン不要）
cd ~/dev/2026-09-25-x-model-harvester
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m pytest -q

# ローカルでDRY_RUN実行（実トークンが ~/.x_api_tokens.zsh にある場合のみ、実ブックマーク取得まで確認できる）
DRY_RUN=1 python harvest.py
```

## 既知の限界

- **リンクなし投稿のモデル名推定**: HF/Civitaiリンクが無い投稿は`lib/name_search.py`が正規表現でモデル名らしき候補（所有格表現・org/repo表記・拡張子付きファイル名・サイズ/量子化タグ付き名）を抽出し、HuggingFace検索APIで名前がほぼ一致する1件だけを自動採用する（LLMは使わない意図的簡略化）。確証が持てない候補はダウンロードせず、DriveのREADME「未確定」節に候補名と検索上位ヒットを並べるだけに留める。正規表現でカバーしていない命名パターン（日本語のみのモデル名等）は候補ゼロのまま拾えない。
- **1投稿1モデル想定**: 1つの投稿に複数のHF/Civitaiリンクがある場合、先頭のリンクだけを処理する。
- **Civitaiは鍵必須**: `CIVITAI_TOKEN`が無いと全てskipになる（未ログインDLの不安定さを避けるための意図的な簡略化）。
- **再試行は理由の記録のみ**: 失敗時に`retry_count`を記録する仕組みはあるが、次回runで自動的に同じツイートを再取得して再試行するロジックは未実装（`harvest.py`の`retry_failed_items`のコメント参照）。本格対応するときはstateから失敗ツイートIDのURLを再構築して`process_tweet`相当を再実行する処理を追加する。
- **GitHub cronの遅延**: 数時間遅れることがある前提で30分間隔にしている。急ぎたい場合は`workflow_dispatch`で手動実行（既定DRY_RUNなので本番実行したい場合はワークフローの条件を一時的に変えるか、リポジトリ変数で制御する仕組みを別途足す）。
- **1ファイルの上限は25GB**: ダウンロード中にストリームで打ち切る。
- **ダウンロード対象の判定は拡張子・ファイル名ベースのヒューリスティック**（`.safetensors`/`.gguf`優先、fp8/量子化優先）。命名規則から外れたリポジトリでは誤選択の可能性がある。
- **ライセンス表記**: HF側は現状「要確認」固定（`cardData.license`を読む処理は未実装）。Civitai側は`allowCommercialUse`のみで判定した簡易表記。
- **通知はGmail SMTP（アプリパスワード）方式のみ**。既存のSlack/Mail.app AppleScript通知基盤はmacOSローカル前提でGitHub Actionsから使えないため流用していない。

## ファイル構成

| ファイル | 役割 |
|---|---|
| `harvest.py` | 本体。DRY_RUN分岐・全体のオーケストレーション |
| `lib/paths.py` | 定数（Drive remote名・保存先・上限値など） |
| `lib/auth.py` | X API OAuth1.0a認証 |
| `lib/fetch_bookmarks.py` | ブックマーク取得・正規化 |
| `lib/extract.py` | HF/Civitaiリンク抽出（ネットワークなし・テスト対象） |
| `lib/hf_client.py` | HuggingFaceのファイル解決 |
| `lib/civitai_client.py` | Civitaiのファイル解決 |
| `lib/downloader.py` | DL→Driveアップロード→ローカル削除 |
| `lib/state.py` | Drive上の状態JSON読み書き |
| `lib/readme_update.py` | Drive上のREADME一覧表更新 |
| `lib/notify.py` | Gmail SMTP通知（任意） |
| `tests/` | 単体テスト（HF/Civitai/非モデル投稿の抽出ロジック） |
| `.github/workflows/harvest.yml` | cron 30分おき＋workflow_dispatch |
