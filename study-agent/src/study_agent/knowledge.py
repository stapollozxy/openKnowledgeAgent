from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .db import Store


def knowledge_root() -> Path:
    configured = os.getenv("STUDY_AGENT_KNOWLEDGE_HOME")
    return Path(configured or "knowledge").expanduser().resolve()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content.rstrip() + "\n", encoding="utf-8")
    temporary.replace(path)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return slug[:48] or "session"


def _text(value: Any, fallback: str = "尚无证据") -> str:
    return str(value).strip() if value not in (None, "") else fallback


def _bullets(values: list[Any] | None) -> str:
    values = values or []
    return "\n".join(f"- {_text(value)}" for value in values) or "- 尚无证据"


def render_insight_markdown(payload: dict[str, Any], generated_at: str) -> str:
    lines = [
        "# Open Knowledge Agent Insights",
        "",
        f"> Generated: {generated_at}",
        "> Source: local chats, tasks, check-ins, evidence, and configured GitHub repository.",
        "",
        "## Overview",
        "",
        _text(payload.get("overview")),
        "",
        "## Strengths",
        "",
        _bullets(payload.get("strengths")),
        "",
        "## Knowledge Gaps",
        "",
    ]
    for item in payload.get("gaps", []):
        lines.extend([
            f"### {_text(item.get('topic'), 'Unlabeled gap')}",
            "",
            f"- Why it matters: {_text(item.get('why'))}",
            f"- Evidence: {_text(item.get('evidence'))}",
            "",
        ])
    lines.extend(["## Meaningful Questions", ""])
    for index, item in enumerate(payload.get("meaningful_questions", []), 1):
        lines.extend([
            f"### Q{index}. {_text(item.get('question'), 'Untitled question')}",
            "",
            f"- Why it matters: {_text(item.get('why_it_matters'))}",
            f"- Missing concept: {_text(item.get('missing_concept'))}",
            f"- Review prompt: {_text(item.get('review_prompt'))}",
            "",
        ])
    lines.extend(["## What to Learn Next", ""])
    for item in payload.get("next_learning", []):
        lines.extend([
            f"### P{item.get('priority', '?')}. {_text(item.get('topic'), 'Next topic')}",
            "",
            f"- Why: {_text(item.get('why'))}",
            f"- Next action: {_text(item.get('next_action'))}",
            f"- Done when: {_text(item.get('done_when'))}",
            "",
        ])
    lines.extend(["## Industry Projects", ""])
    for item in payload.get("industry_projects", []):
        lines.extend([
            f"### {_text(item.get('name'), 'Industry project')}",
            "",
            _text(item.get("industrial_use")),
            "",
            "**Architecture**",
            "",
            _bullets(item.get("architecture")),
            "",
            "**Milestones**",
            "",
            _bullets(item.get("milestones")),
            "",
            "**Metrics**",
            "",
            _bullets(item.get("metrics")),
            "",
            "**Resume evidence**",
            "",
            _text(item.get("resume_evidence")),
            "",
        ])
    return "\n".join(lines)


def _render_questions(payload: dict[str, Any], generated_at: str) -> str:
    lines = ["# Meaningful Questions Notebook", "", f"> Updated: {generated_at}", ""]
    for index, item in enumerate(payload.get("meaningful_questions", []), 1):
        lines.extend([
            f"## Q{index}. {_text(item.get('question'), 'Untitled question')}",
            "",
            f"- Learning/practical value: {_text(item.get('why_it_matters'))}",
            f"- Concept to repair: {_text(item.get('missing_concept'))}",
            f"- Retrieval-practice prompt: {_text(item.get('review_prompt'))}",
            "",
        ])
    return "\n".join(lines)


def _render_roadmap(payload: dict[str, Any], generated_at: str) -> str:
    lines = ["# Learning Roadmap", "", f"> Updated: {generated_at}", ""]
    for item in payload.get("next_learning", []):
        lines.extend([
            f"## P{item.get('priority', '?')}. {_text(item.get('topic'), 'Next topic')}",
            "",
            f"- Reason: {_text(item.get('why'))}",
            f"- Action: {_text(item.get('next_action'))}",
            f"- Definition of done: {_text(item.get('done_when'))}",
            "",
        ])
    return "\n".join(lines)


def _render_projects(payload: dict[str, Any], generated_at: str) -> str:
    subset = {"overview": "Industrial project candidates", "industry_projects": payload.get("industry_projects", [])}
    markdown = render_insight_markdown(subset, generated_at)
    return markdown.replace("# Open Knowledge Agent Insights", "# Industry Project Portfolio", 1)


def _mermaid_label(value: Any) -> str:
    return _text(value, "Unknown").replace('"', "'").replace("\n", " ")[:80]


def _render_graph(store: Store, payload: dict[str, Any], generated_at: str) -> str:
    profile = store.profile() or {}
    lines = [
        "# Learning Knowledge Graph",
        "",
        f"> Updated: {generated_at}",
        "",
        "```mermaid",
        "graph TD",
        f'  Goal["{_mermaid_label(profile.get("goal"))}"]',
    ]
    for index, topic in enumerate(store.topics(), 1):
        lines.extend([
            f'  Group{index}["{_mermaid_label(topic.get("name"))}"]',
            f"  Goal --> Group{index}",
        ])
    for index, item in enumerate(payload.get("next_learning", []), 1):
        lines.extend([
            f'  Learning{index}["{_mermaid_label(item.get("topic"))}"]',
            f"  Goal --> Learning{index}",
        ])
    for index, item in enumerate(payload.get("industry_projects", []), 1):
        lines.extend([
            f'  Project{index}["{_mermaid_label(item.get("name"))}"]',
            f"  Goal --> Project{index}",
        ])
    for index, item in enumerate(payload.get("meaningful_questions", []), 1):
        target = ((index - 1) % max(1, len(payload.get("next_learning", [])))) + 1
        lines.append(f'  Question{index}["{_mermaid_label(item.get("question"))}"]')
        if payload.get("next_learning"):
            lines.append(f"  Question{index} --> Learning{target}")
        else:
            lines.append(f"  Question{index} --> Goal")
    lines.extend([
        "```",
        "",
        "## Portable knowledge files",
        "",
        "- [Latest insights](insights/latest.md)",
        "- [Questions notebook](questions.md)",
        "- [Learning roadmap](learning-roadmap.md)",
        "- [Industry projects](industry-projects.md)",
        "- [Conversation history](sessions/)",
    ])
    return "\n".join(lines)


def _export_sessions(store: Store, root: Path) -> list[Path]:
    written: list[Path] = []
    for session in store.sessions(limit=200):
        path = root / "sessions" / _slug(session.get("topic_name") or "General") / f"session-{session['id']:04d}-{_slug(session['title'])}.md"
        lines = [
            f"# {session['title']}",
            "",
            f"> Topic: {session.get('topic_name') or 'General'} · Session ID: {session['id']} · Updated: {session['updated_at']}",
            "",
        ]
        for message in store.messages(session["id"], limit=1000):
            speaker = "User" if message["role"] == "user" else "Open Knowledge Agent"
            lines.extend([f"## {speaker}", "", message["content"], ""])
        _write(path, "\n".join(lines))
        written.append(path)
    return written


def export_knowledge(store: Store, payload: dict[str, Any], root: Path | None = None) -> list[Path]:
    root = root or knowledge_root()
    current = datetime.now().astimezone()
    generated_at = current.isoformat(timespec="seconds")
    snapshot = root / "insights" / f"{current.strftime('%Y-%m-%d_%H%M%S')}.md"
    latest = root / "insights" / "latest.md"
    insight_markdown = render_insight_markdown(payload, generated_at)
    _write(snapshot, insight_markdown)
    _write(latest, insight_markdown)
    files = [snapshot, latest]

    fixed = {
        root / "questions.md": _render_questions(payload, generated_at),
        root / "learning-roadmap.md": _render_roadmap(payload, generated_at),
        root / "industry-projects.md": _render_projects(payload, generated_at),
        root / "knowledge-graph.md": _render_graph(store, payload, generated_at),
        root / "insights" / "latest.json": json.dumps(payload, ensure_ascii=False, indent=2),
    }
    for path, content in fixed.items():
        _write(path, content)
        files.append(path)
    session_files = _export_sessions(store, root)
    files.extend(session_files)

    index_lines = [
        "# Open Knowledge Agent Knowledge Base",
        "",
        "This directory is portable. Point another app or agent at this README, or ingest the whole folder.",
        "",
        f"> Last export: {generated_at}",
        "",
        "## Core knowledge",
        "",
        "- [Knowledge graph](knowledge-graph.md)",
        "- [Latest insights](insights/latest.md)",
        "- [Questions notebook](questions.md)",
        "- [Learning roadmap](learning-roadmap.md)",
        "- [Industry projects](industry-projects.md)",
        "",
        "## Insight history",
        "",
    ]
    for path in sorted((root / "insights").glob("20*.md"), reverse=True):
        index_lines.append(f"- [{path.stem}](insights/{path.name})")
    index_lines.extend(["", "## Conversation history", ""])
    for path in session_files:
        relative = path.relative_to(root).as_posix()
        index_lines.append(f"- [{path.stem}]({relative})")
    _write(root / "README.md", "\n".join(index_lines))
    files.append(root / "README.md")
    return files


def remove_session_export(session_id: int, root: Path | None = None) -> None:
    root = root or knowledge_root()
    prefix = f"session-{session_id:04d}-"
    for path in (root / "sessions").rglob(f"{prefix}*.md"):
        path.unlink(missing_ok=True)
    index = root / "README.md"
    if index.is_file():
        lines = [line for line in index.read_text(encoding="utf-8").splitlines() if prefix not in line]
        _write(index, "\n".join(lines))
