from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _token() -> str | None:
    configured = os.getenv("STUDY_AGENT_GH_PATH")
    if configured:
        executable = configured if os.path.isfile(configured) else None
    else:
        token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        if token:
            return token
        executable = shutil.which("gh")
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, "auth", "token", "--hostname", "github.com"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _get(path: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "study-agent/0.1",
    }
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://api.github.com{path}", headers=headers, method="GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API returned {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach GitHub: {exc.reason}") from exc


def repository_summary(repo: str) -> dict[str, Any]:
    if not REPO_PATTERN.fullmatch(repo):
        raise ValueError("GitHub repository must use owner/repo format")
    encoded = urllib.parse.quote(repo, safe="/")
    metadata = _get(f"/repos/{encoded}")
    commits = _get(f"/repos/{encoded}/commits?per_page=5")
    pulls = _get(f"/repos/{encoded}/pulls?state=open&per_page=5")
    issues = _get(f"/repos/{encoded}/issues?state=open&per_page=5")
    issues = [item for item in issues if "pull_request" not in item]
    return {
        "repo": repo,
        "description": metadata.get("description"),
        "default_branch": metadata.get("default_branch"),
        "updated_at": metadata.get("updated_at"),
        "commits": [
            {
                "sha": item.get("sha", "")[:7],
                "message": item.get("commit", {}).get("message", "").splitlines()[0],
                "date": item.get("commit", {}).get("author", {}).get("date"),
            }
            for item in commits
        ],
        "open_prs": [
            {"number": item.get("number"), "title": item.get("title")}
            for item in pulls
        ],
        "open_issues": [
            {"number": item.get("number"), "title": item.get("title")}
            for item in issues
        ],
    }

