#!/usr/bin/env python3
"""Refresh README tokens and inject latest commits."""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
from pathlib import Path
import json
from typing import Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
RECENT_COMMITS_START = "<!--RECENT_COMMITS-->"
RECENT_COMMITS_END = "<!--/RECENT_COMMITS-->"
STATS_VERSION_START = "<!--STATS_VERSION-->"
STATS_VERSION_END = "<!--/STATS_VERSION-->"
LAST_UPDATED_START = "<!--LAST_UPDATED-->"
LAST_UPDATED_END = "<!--/LAST_UPDATED-->"


class ReadmeUpdaterError(RuntimeError):
    pass


def _iso_to_human(ts: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return ts
    return parsed.strftime("%d/%m/%Y %H:%M UTC")


def fetch_recent_commits(username: str, limit: int = 5) -> List[Dict[str, str]]:
    """Return up to ``limit`` recent commits from public push events."""
    url = f"https://api.github.com/users/{username}/events/public"
    headers = {
        "Accept": "application/vnd.github+json",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers)
    with urlopen(request, timeout=15) as response:
        events = json.loads(response.read().decode("utf-8"))

    commits: List[Dict[str, str]] = []
    seen = set()
    for event in events:
        if event.get("type") != "PushEvent":
            continue
        repo = event.get("repo", {}).get("name", "")
        created_at = event.get("created_at", "")
        human_time = _iso_to_human(created_at) if created_at else ""
        for commit in event.get("payload", {}).get("commits", []):
            sha = commit.get("sha")
            if not sha or sha in seen:
                continue
            seen.add(sha)
            message = (commit.get("message") or "Commit sem mensagem").splitlines()[0]
            commits.append(
                {
                    "message": message,
                    "repo": repo,
                    "url": f"https://github.com/{repo}/commit/{sha}",
                    "timestamp": human_time,
                }
            )
            if len(commits) >= limit:
                return commits
    return commits


def replace_block(content: str, start: str, end: str, replacement: str) -> str:
    pattern = re.compile(
        rf"{re.escape(start)}.*?{re.escape(end)}",
        re.DOTALL,
    )
    new_block = f"{start}\n{replacement}\n{end}"
    new_content, count = pattern.subn(new_block, content)
    if count == 0:
        raise ReadmeUpdaterError(f"Marcadores {start} ... {end} não encontrados no README")
    return new_content


def build_commit_section(commits: List[Dict[str, str]]) -> str:
    if not commits:
        return "- _Nenhum commit público recente disponível no momento._"
    lines = []
    for commit in commits:
        timestamp = f" • {commit['timestamp']}" if commit["timestamp"] else ""
        lines.append(
            f"- [{commit['message']}]({commit['url']}) ({commit['repo']}{timestamp})"
        )
    return "\n".join(lines)


def main() -> int:
    readme = README_PATH.read_text(encoding="utf-8")
    version_token = dt.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    human_ts = dt.datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")
    username = os.environ.get("TARGET_USERNAME", "vitorazevedop7")

    try:
        commits = fetch_recent_commits(username)
    except HTTPError as exc:
        print(f"Falha ao buscar commits: {exc}", file=sys.stderr)
        commits = []
    except URLError as exc:
        print(f"Erro de rede ao buscar commits: {exc}", file=sys.stderr)
        commits = []

    updated = readme
    updated = replace_block(updated, STATS_VERSION_START, STATS_VERSION_END, version_token)
    updated = replace_block(updated, LAST_UPDATED_START, LAST_UPDATED_END, human_ts)
    updated = replace_block(updated, RECENT_COMMITS_START, RECENT_COMMITS_END, build_commit_section(commits))

    README_PATH.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
