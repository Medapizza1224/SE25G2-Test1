#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ci_review.py（CI 用レビュースクリプト）

概要（やること）
1) PR で変更された docs/SRS/*.md を収集
2) 各 SRS に行番号を付与（例: "0001│ ...")
3) review_runner.py の仕様に合わせ、repo ルートの srs/ に“一時コピー”
   ↳ review_runner.py は「--srs <ファイル名>」で srs/ を参照
4) review_runner.py を起動（モデルや出力形式は review_runner 側に準拠）
5) 生成 JSON を読み取り、PR にコメント投稿（総評1件＋行コメント複数）

使い方（ローカル検証・CI 共通の考え方）
- 既定: review_runner.py の MODELS/SRS 設定をそのまま使用（“コマンドで必須指定しない”方針）
    python generate_review/ci_review.py
- 必要時だけモデルを一時上書き（任意）
    python generate_review/ci_review.py --models gpt-5-mini,gpt-4.1

環境変数（CI から受け取り）
- REPO, PR_NUMBER, GITHUB_TOKEN（必須）

備考
- 日本語は UTF-8 のまま送信。requests はデフォルトで UTF-8 を扱えるため追加設定は不要です。
"""

from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from collections import deque
from typing import Dict, Any, List, Tuple, Optional

import difflib
import requests

# ========= 基本パス =========
ROOT = Path(__file__).resolve().parents[1]          # リポジトリルート
SRS_INPUT_DIR = ROOT / "docs" / "SRS"               # 変更検出対象ディレクトリ
SRS_STAGING_DIR = ROOT / "srs"                       # ★review_runner が読む場所（A案：ここへ一時コピー）
RESULT_DIR = ROOT / "generate_review_result"         # review_runner の出力置き場
RUNNER = ROOT / "generate_review" / "review_runner.py"  # 既存スクリプト

# ========= ログ =========
# 直近ログの簡易リングバッファ（失敗通知に貼る用）
LOG_RING: deque[str] = deque(maxlen=1000)
def info(msg: str) -> None:
    print(f"[ci_review] {msg}", flush=True)
    try:
        LOG_RING.append(f"[INFO] {msg}")
    except Exception:
        pass

def warn(msg: str) -> None:
    print(f"[ci_review][warn] {msg}", flush=True)
    try:
        LOG_RING.append(f"[WARN] {msg}")
    except Exception:
        pass

# ========= GitHub API（薄いラッパ：簡易リトライ） =========
def gh_get(url: str, token: str, params: Optional[Dict[str, Any]] = None, max_tries: int = 3):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    for i in range(1, max_tries+1):
        try:
            r = requests.get(url, headers=headers, params=params or {})
            # 2xx 以外は raise_for_status で例外化
            r.raise_for_status()
            return r
        except Exception as e:
            if i == max_tries:
                raise
            warn(f"GET retry {i}/{max_tries-1} after error: {e}")
            time.sleep(1.0 * i)

def gh_post(url: str, token: str, payload: Dict[str, Any], max_tries: int = 3):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    for i in range(1, max_tries+1):
        try:
            r = requests.post(url, headers=headers, json=payload)
            # 2xx 以外は例外化（本文も出す）
            if r.status_code >= 300:
                raise RuntimeError(f"POST {url} failed: {r.status_code} {r.text}")
            return r
        except Exception as e:
            if i == max_tries:
                raise
            warn(f"POST retry {i}/{max_tries-1} after error: {e}")
            time.sleep(1.0 * i)

# ========= PR 差分から docs/SRS/*.md を取得 =========
def get_changed_files(repo: str, pr_number: int, token: str) -> List[Dict[str, Any]]:
    """
    GitHub API: GET /repos/{owner}/{repo}/pulls/{pull_number}/files
    戻り値の各要素には filename/status/patch などが入る。
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"
    files = []
    page = 1
    while True:
        r = gh_get(url, token, params={"page": page, "per_page": 100})
        batch = r.json()
        files.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return files

# ========= 行番号付与（0001│ のようなフォーマット） =========
def number_srs(src: Path) -> Path:
    """
    入力: docs/SRS/*.md の実ファイル
    出力: /tmp に作る一時ファイル（中身は行番号付与済み）
    """
    lines = src.read_text(encoding="utf-8").splitlines()
    numbered = "\n".join(f"{i:04d}│ {line}" for i, line in enumerate(lines, 1))
    tmp = Path(tempfile.gettempdir()) / f"numbered_{src.name}"
    tmp.write_text(numbered, encoding="utf-8")
    return tmp

# ========= 既存 review_runner の起動（A案の核心） =========
def run_review_runner_with_staged_file(staged_name: str, models_arg: Optional[str]) -> None:
    """
    review_runner.py は従来どおり「--srs <ファイル名>」で srs/ を参照する前提。
    - staged_name には SRS_STAGING_DIR に置いた“一時ファイル名”を渡す
    - cwd=ROOT で起動し、相対パス参照（input_prompt など）を安全にする
    """
    cmd = [sys.executable, str(RUNNER), "--srs", staged_name]
    if models_arg:
        # 任意。指定があれば review_runner のハードコード設定を上書き可能
        cmd += ["--models", models_arg]

    info("$ " + " ".join(cmd))
    # 出力を捕捉しつつ実行（失敗通知にログを添付できるように）
    p = subprocess.run(
        cmd,
        check=True,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if p.stdout:
        for ln in p.stdout.splitlines():
            print(ln)
            try:
                LOG_RING.append(f"[runner][out] {ln}")
            except Exception:
                pass
    if p.stderr:
        for ln in p.stderr.splitlines():
            print(ln, file=sys.stderr)
            try:
                LOG_RING.append(f"[runner][err] {ln}")
            except Exception:
                pass

# ========= JSON の収集（簡易） =========
def collect_result_jsons() -> List[Path]:
    """
    review_runner の出力先（generate_review_result/*.json）から JSON をすべて拾う。
    """
    RESULT_DIR.mkdir(exist_ok=True)
    return sorted(RESULT_DIR.glob("*.json"))

def pick_latest_result_jsons_for_stem(stem: str) -> list[Path]:
    """
    過去の結果は残しつつ、今回PRのSRS（stem）に対応する JSON だけを採用。
    さらに「モデルごとに最新の1件」に絞る。
      例: se24g2__gpt-5.json, se24g2__gpt-4.1.json の “最新版” だけ。
    """
    candidates = sorted(
        RESULT_DIR.glob(f"{stem}__*.json"), 
        key=lambda p: p.stat().st_mtime, 
        reverse=True
    )
    latest_per_model: dict[str, Path] = {}
    for p in candidates:
        # ファイル名: "<stem>__<model>.json" という前提でモデル名を取り出す
        # 例: "se24g2__gpt-5.json" → model = "gpt-5"
        name = p.name
        try:
            model = name.split("__", 1)[1].rsplit(".", 1)[0]
        except Exception:
            # 予期せぬ命名のものは弾く
            continue
        if model not in latest_per_model:
            latest_per_model[model] = p  # mtime降順に見ているので最初が最新
    return list(latest_per_model.values())

# ========= 抜粋から元SRSの行番号を推定 =========
def find_lineno_by_excerpt(original_lines: List[str], excerpt: str) -> Optional[int]:
    """
    - モデル出力 'line' は“抜粋テキスト”として想定
    - まず部分一致 → 見つからなければ簡易類似度で推定
    """
    ex = (excerpt or "").strip()
    if not ex:
        return None
    # 部分一致の最初のヒット
    for i, ln in enumerate(original_lines, start=1):
        if ex in ln:
            return i
    # 類似度で推定
    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s or "").strip()
    exn = norm(ex)
    best_i, best_score = None, 0.0
    for i, ln in enumerate(original_lines, start=1):
        score = difflib.SequenceMatcher(None, exn, norm(ln)).ratio()
        if score > best_score:
            best_score = score; best_i = i
    return best_i if (best_i and best_score >= 0.6) else None

# ========= コメント投稿（堅いやり方：総評＝通常コメント／行は個別） =========
def post_issue_comment(repo: str, pr_number: int, token: str, body: str) -> None:
    """
    PR の「会話」タブに通常コメントを 1 件投稿。
    """
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    gh_post(url, token, {"body": body})

def get_pr_head_sha(repo: str, pr_number: int, token: str) -> str:
    """
    最新 HEAD の commit sha を取得。行コメントで commit_id として必須。
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    r = gh_get(url, token)
    return r.json()["head"]["sha"]

def post_inline_comment(repo: str, pr_number: int, token: str,
                        commit_sha: str, path: str, line: int, body: str) -> None:
    """
    PR の「行コメント」を 1 件投稿。
    - 新規ファイル前提: path（ファイルパス）, side=RIGHT, line=行番号 が使える
    - まとめてレビュー API は position 指定等が面倒なため、1件ずつ確実に投げる
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments"
    payload = {
        "commit_id": commit_sha,
        "path": path,
        "side": "RIGHT",
        "line": int(line),
        "body": body,
    }
    gh_post(url, token, payload)
    
def post_pull_review(repo: str, pr_number: int, token: str, review_body: str, review_comments: list[dict]) -> None:
    """
    一括レビュー投稿：
      - review_body   : ジェネラル（総評）
      - review_comments: インラインコメントの配列
        形式: {"path": "docs/SRS/se24g2.md", "line": 12, "side": "RIGHT", "body": "本文"}
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
    payload = {
        "body": review_body or "",
        "event": "COMMENT",     # 単なるコメントレビュー。必要なら "REQUEST_CHANGES" なども可
        "comments": review_comments
    }
    gh_post(url, token, payload)

def _sanitize_fence(s: str) -> str:
    """フェンスコード内で壊れないよう最低限のサニタイズ。"""
    s = (s or "").strip()
    # ``` が入ってくるとフェンスが壊れるので弱める（バッククォートの間にゼロ幅スペース）
    return s.replace("```", "``\u200b`")

def render_ai_review_comment(excerpt: str, detail: str, axes: Optional[List[str]] = None) -> str:
    """
    GitHubのMarkdownで見た目が安定するように整形。
    - 見出しは ### で段落を分ける
    - excerpt は複数行も安全な ```text フェンスで囲む
    - 前後に空行を入れて、装飾の“伝播”を防ぐ
    """
    ex = _sanitize_fence(excerpt)
    dt = (detail or "").strip()
    ax = ", ".join(axes or [])

    parts = [
        "### AI Review",   # ← 太字ではなく見出しに
        "",
        ("**axes:** " + ax) if ax else "",
        "",
        "**excerpt:**",
        "```text",
        ex,
        "```",
        "",
        dt,
    ]
    # 空要素を除去してから結合（余計な空行を防ぐ）
    return "\n".join([p for p in parts if p != ""]) 

# ========= メイン =========
def main():
    # ---- CLI：--models は任意（未指定なら review_runner のデフォルトを使う） ----
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=None, help="任意。指定時は review_runner のモデル設定を上書き（例: gpt-5-mini,gpt-4.1-mini）")
    args = ap.parse_args()

    # ---- 環境変数（GitHub Actions から受け取る）----
    repo = os.environ.get("REPO")
    pr_number = int(os.environ.get("PR_NUMBER", "0"))
    token = os.environ.get("GITHUB_TOKEN")
    if not (repo and pr_number and token):
        print("REPO / PR_NUMBER / GITHUB_TOKEN の環境変数が必要です。", file=sys.stderr)
        sys.exit(2)

    info(f"Repo: {repo}, PR: {pr_number}")

    # ---- PR 変更ファイル一覧 → docs/SRS/*.md のみ抽出 ----
    files = get_changed_files(repo, pr_number, token)
    srs_files = [f for f in files if f["filename"].startswith("docs/SRS/") and f["filename"].endswith(".md")]
    if not srs_files:
        info("No SRS files changed. Exit.")
        return

    # ---- 行番号付与 & srs/ に一時コピー（review_runner の期待に合わせる）----
    SRS_STAGING_DIR.mkdir(exist_ok=True)
    staged_names: List[str] = []  # review_runner に渡すファイル名リスト

    for f in srs_files:
        repo_rel = f["filename"]                      # 例: "docs/SRS/se24g2.md"
        src_path = ROOT / repo_rel
        if not src_path.exists():
            warn(f"Missing on disk (checkout?): {src_path}")
            continue

        # 1) 行番号付き一時ファイルを作成（/tmp）
        numbered_tmp = number_srs(src_path)
        info(f"Numbered SRS: {repo_rel} -> {numbered_tmp}")

        # 2) srs/ に“一時コピー”。ファイル名は衝突防止のため接頭辞を付与
        staged_name = f"ci_numbered__{Path(repo_rel).name}"
        staged_path = SRS_STAGING_DIR / staged_name
        staged_path.write_text(numbered_tmp.read_text(encoding="utf-8"), encoding="utf-8")
        info(f"Staged for review_runner: {staged_path}")
        staged_names.append(staged_name)

    # ---- review_runner をファイルごとに実行（失敗しても他は続行）----
    for staged_name in staged_names:
        try:
            run_review_runner_with_staged_file(staged_name, args.models)
        except subprocess.CalledProcessError as e:
            warn(f"review_runner failed for {staged_name}: {e}")

    # ---- 後片付け（srs/ 内の一時ファイルを削除）----
    for staged_name in staged_names:
        p = SRS_STAGING_DIR / staged_name
        try:
            p.unlink()
            info(f"Cleaned staged file: {p}")
        except Exception as e:
            warn(f"cleanup failed: {e}")

    # ---- 結果JSONを収集して、PRへコメント投稿（総評1件＋行コメント複数）----
    result_paths = collect_result_jsons()
    if not result_paths:
        warn("No review JSON found. Nothing to comment.")
        return

    # PR 最新の commit sha（行コメントで必須）
    head_sha = get_pr_head_sha(repo, pr_number, token)

    overall_chunks: List[str] = []
    inline_comments: List[Dict[str, Any]] = []

    # ファイルごとに、対応する JSON を探して投稿内容を作る
    # 簡単化のため、"対象SRSの stem がファイル名に含まれる JSON" をひとまとめに扱う
    for f in srs_files:
        repo_rel = f["filename"]                     # "docs/SRS/se24g2.md"
        stem = Path(repo_rel).stem                   # "se24g2"
        disk_lines = (ROOT / repo_rel).read_text(encoding="utf-8").splitlines()

        # 対応する最新のJSONだけを全回収
        related = pick_latest_result_jsons_for_stem(stem)
        if not related:
            continue

        for jp in related:
            try:
                data = json.loads(jp.read_text(encoding="utf-8"))
            except Exception as e:
                warn(f"invalid json: {jp} ({e})")
                continue

            # 総評（キー名は overall / summary のどちらか想定）
            overall = data.get("overall") or data.get("summary") or ""
            if overall:
                overall_chunks.append(f"**{repo_rel}**\n{overall}")

            # コメント本体（スキーマ差対応：review_items / comments）
            items = data.get("review_items") or data.get("comments") or []
            for it in items:
                excerpt = (it.get("line") or "").strip()          # 抜粋テキストとしての 'line'
                detail = it.get("comment") or it.get("detail") or ""  # 本文
                axes = it.get("axis") or it.get("axes") or []         # 評価軸（C/R/A/F/T/N）
                if not excerpt or not detail:
                    continue
                # 行番号はスキーマ拡張で 'lineno' があればそれを優先、なければ逆引き
                lineno = it.get("lineno")
                if not lineno:
                    lineno = find_lineno_by_excerpt(disk_lines, excerpt) or 1

                body = render_ai_review_comment(excerpt, detail, axes)

                inline_comments.append({
                    "path": repo_rel,
                    "line": int(lineno),
                    "body": body,
                })

    # --- ここまでで作った内容を一括レビューとして投稿 ---
    # 読みやすさのため、総評はやや短く制限（お好みで調整）
    MAX_OVERALL_LEN = 4000
    review_body = ("\n\n".join(overall_chunks))[:MAX_OVERALL_LEN] if overall_chunks else ""

    # Abuse回避・UI可読性のため、インラインも上限をかける（必要に応じて調整）
    MAX_INLINE = 80
    review_comments_payload = []
    for c in inline_comments[:MAX_INLINE]:
        review_comments_payload.append({
            "path": c["path"],     # 例: "docs/SRS/se24g2.md"
            "line": int(c["line"]),# 1始まりの行番号（HEAD側の行）
            "side": "RIGHT",       # 追加行は "RIGHT" 側に付ける（HEAD＝変更後）
            "body": c["body"]
        })

    # 1回のPOSTで総評＋インラインをまとめて送る
    try:
        post_pull_review(repo, pr_number, token, review_body, review_comments_payload)
        info(f"Posted review: overall={'yes' if review_body else 'no'}, inline={len(review_comments_payload)}")
    except Exception as e:
        # 一括レビュー投稿に失敗した場合：乱射をやめ、失敗通知を1件だけPRに投稿する
        warn(f"post_pull_review failed: {e}")

        # Actions 実行ログへのリンク（閲覧しやすいように提示）
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        repo_env = os.environ.get("GITHUB_REPOSITORY", repo)
        run_id = os.environ.get("GITHUB_RUN_ID")
        run_url = f"{server}/{repo_env}/actions/runs/{run_id}" if run_id else None

        # 失敗の要約コメントを作成（例外メッセージと件数、ログURL、ログ抜粋）
        lines = [
            "CI レビューの投稿に失敗しました。詳細を確認してください。",
            "",
            "- 失敗理由 (例外):",
            "```text",
            str(e),
            "```",
            f"- 総評の有無: {'あり' if review_body else 'なし'}",
            f"- インライン予定件数: {len(review_comments_payload)}",
        ]
        if run_url:
            lines += ["", f"Actions の実行ログ: {run_url}"]
        # 直近ログ（末尾120行）を添付
        try:
            tail_lines = list(LOG_RING)[-120:]
            if tail_lines:
                lines += [
                    "",
                    "- ログ抜粋 (末尾 120 行):",
                    "```text",
                    _sanitize_fence("\n".join(tail_lines)),
                    "```",
                ]
        except Exception:
            pass

        lines += [
            "",
            "必要に応じて PR にラベル `ci-review` を付け直して再実行してください。",
        ]

        try:
            post_issue_comment(repo, pr_number, token, "\n".join(lines))
            info("Posted failure notice comment instead of inline fallback.")
        except Exception as e2:
            warn(f"failed to post failure notice: {e2}")


    # # 1) 総評：PR の通常コメントとして 1 件にまとめて投稿
    # if overall_chunks:
    #     post_issue_comment(repo, pr_number, token, "\n\n".join(overall_chunks)[:60000])
    #     info(f"Posted overall comment ({len(overall_chunks)} parts).")

    # # 2) 行コメント：commit_id 必須。1件ずつ投稿（新規ファイル前提で最も壊れにくい）
    # posted = 0
    # for c in inline_comments[:80]:  # 過剰投稿防止のため軽く上限
    #     try:
    #         post_inline_comment(repo, pr_number, token, head_sha, c["path"], c["line"], c["body"])
    #         posted += 1
    #     except Exception as e:
    #         warn(f"inline comment failed: {e}")

    # info(f"Posted inline comments: {posted}/{len(inline_comments)}")

if __name__ == "__main__":
    main()
