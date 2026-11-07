from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from .agent import direct_chat_payload, extract_profile_update, insights_payload, run_agent
from .calendar import create_event, list_events
from .db import Store
from .system_clock import system_time
from .knowledge import export_knowledge, knowledge_root, remove_session_export
from .transfer import export_bundle, import_bundle


def load_env(path: Path = Path(".env")) -> None:
    """Load a small project-local .env file without overriding shell variables."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key.replace("_", "").isalnum():
            os.environ.setdefault(key, value)


def home_dir() -> Path:
    return Path(os.getenv("STUDY_AGENT_HOME", ".study-agent")).expanduser().resolve()


def store() -> Store:
    return Store(home_dir() / "agent.db")


def require_profile(db: Store) -> dict:
    profile = db.profile()
    if not profile:
        db.save_profile("", None, 10, None)
        profile = db.profile()
    if not profile:
        raise RuntimeError("Could not initialize the local profile.")
    return profile


def call_agent(
    db: Store,
    message: str,
    conversation: list[dict] | None = None,
    topic_name: str = "General",
) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY before running the agent.")
    return asyncio.run(
        run_agent(db, message, conversation=conversation, topic_name=topic_name)
    )


def cmd_init(args: argparse.Namespace) -> None:
    db = store()
    db.save_profile(
        goal=args.goal,
        deadline=args.deadline,
        weekly_hours=args.weekly_hours,
        github_repo=args.github,
        course_progress=args.progress,
        course=args.course,
    )
    print(f"Initialized study agent at {db.path}")


def cmd_today(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    if args.progress:
        db.update_progress(args.progress)
    payload = {
        "available_minutes": args.minutes,
        "course_progress": args.progress,
        "note": args.note,
    }
    db.save_checkin("morning", payload)
    print(call_agent(
        db,
        "生成今天的学习与项目计划。可用时间："
        f"{args.minutes} 分钟。课程进度：{args.progress or '读取 profile'}。"
        f"补充：{args.note or '无'}。请读取 GitHub 和日历后再安排，并把任务写入数据库。",
    ))


def cmd_review(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    payload = {
        "completed": args.completed,
        "blocked": args.blocked,
        "evidence": args.evidence,
        "tomorrow_minutes": args.tomorrow_minutes,
    }
    db.save_checkin("evening", payload)
    print(call_agent(
        db,
        "进行晚间复盘。"
        f"完成：{args.completed or '无'}。"
        f"卡点：{args.blocked or '无'}。"
        f"证据：{args.evidence or '无'}。"
        f"明天可用 {args.tomorrow_minutes} 分钟。"
        "请只把用户明确完成的任务标记完成，只记录真实证据。",
    ))


def cmd_weekly(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    db.save_checkin("weekly", {"note": args.note})
    print(call_agent(db, f"进行周复盘。补充说明：{args.note or '无'}。"))


def cmd_chat(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    session_id = args.session
    if session_id is None:
        session_id = db.create_session(
            args.message[:48] or "New Chat", topic_id=args.topic
        )
    elif not db.session(session_id):
        raise SystemExit(f"Session {session_id} not found.")
    session = db.session(session_id) or {}
    conversation = db.messages(session_id, limit=30)
    response = call_agent(
        db,
        args.message,
        conversation=conversation,
        topic_name=session.get("topic_name") or "General",
    )
    response, changes = extract_profile_update(response)
    proposal = (
        {"changes": changes, "current": db.profile() or {}} if changes else None
    )
    db.add_message(session_id, "user", args.message)
    db.add_message(session_id, "assistant", response)
    if len(conversation) == 0:
        db.rename_session(session_id, args.message[:48])
    if args.json:
        print(json.dumps({
            "session_id": session_id,
            "message": response,
            "profile_update": proposal,
        }, ensure_ascii=False))
    else:
        print(response)


def cmd_chat_context(args: argparse.Namespace) -> None:
    """Prepare a safe, read-only prompt for ChatGPT-plan inference."""
    db = store()
    require_profile(db)
    session_id = args.session
    if session_id is None:
        session_id = db.create_session(
            args.message[:48] or "New Chat", topic_id=args.topic
        )
    elif not db.session(session_id):
        raise SystemExit(f"Session {session_id} not found.")
    session = db.session(session_id) or {}
    conversation = db.messages(session_id, limit=30)
    payload = direct_chat_payload(
        db,
        args.message,
        conversation,
        topic_name=session.get("topic_name") or "General",
    )
    payload["session_id"] = session_id
    print(json.dumps(payload, ensure_ascii=False))


def cmd_chat_save(args: argparse.Namespace) -> None:
    """Persist a completed direct-inference exchange in local SQLite."""
    db = store()
    require_profile(db)
    if not db.session(args.session):
        raise SystemExit(f"Session {args.session} not found.")
    is_first = len(db.messages(args.session, limit=1)) == 0
    response, changes = extract_profile_update(args.assistant)
    proposal = (
        {"changes": changes, "current": db.profile() or {}} if changes else None
    )
    db.add_message(args.session, "user", args.user)
    db.add_message(args.session, "assistant", response)
    if is_first:
        db.rename_session(args.session, args.user[:48])
    print(json.dumps({
        "session_id": args.session,
        "saved": True,
        "message": response,
        "profile_update": proposal,
    }, ensure_ascii=False))


def cmd_profile_update(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    try:
        changes = json.loads(args.changes_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid profile changes JSON: {exc}") from exc
    if not isinstance(changes, dict):
        raise SystemExit("Profile changes must be a JSON object.")
    try:
        profile = db.update_profile(changes)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    labels = {
        "course": "course",
        "course_progress": "course progress",
        "goal": "goal",
    }
    updated = ", ".join(labels[key] for key in changes if key in labels)
    message = f"Saved to long-term profile: {updated}."
    if args.session is not None:
        if not db.session(args.session):
            raise SystemExit(f"Session {args.session} not found.")
        db.add_message(args.session, "assistant", message)
    print(json.dumps({"saved": True, "profile": profile, "message": message}, ensure_ascii=False))


def cmd_auth_status(_: argparse.Namespace) -> None:
    print(json.dumps({"api_key": bool(os.getenv("OPENAI_API_KEY"))}))


def cmd_system_time(_: argparse.Namespace) -> None:
    print(json.dumps(system_time(), ensure_ascii=False))


def cmd_insights_context(_: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    print(json.dumps(insights_payload(db), ensure_ascii=False))


def cmd_insights_current(_: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    print(json.dumps(db.latest_insights(), ensure_ascii=False))


def cmd_insights_save(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Insights payload must be a JSON object")
    snapshot_id = db.save_insights(payload)
    files = export_knowledge(db, payload)
    print(json.dumps({
        "snapshot_id": snapshot_id,
        "saved": True,
        "knowledge_root": str(knowledge_root()),
        "files_written": len(files),
    }))


def cmd_insights_generate(_: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    payload = insights_payload(db)
    print(call_agent(
        db,
        payload["instructions"] + "\n\n真实本地数据：\n" + payload["input"],
    ))


def cmd_knowledge_path(_: argparse.Namespace) -> None:
    print(json.dumps({"path": str(knowledge_root())}, ensure_ascii=False))


def cmd_data_export(args: argparse.Namespace) -> None:
    result = export_bundle(Path(args.source), Path(args.output))
    print(json.dumps(result, ensure_ascii=False))


def cmd_data_import(args: argparse.Namespace) -> None:
    db = store()
    result = import_bundle(Path(args.file), db.path, knowledge_root())
    Store(db.path)
    print(json.dumps(result, ensure_ascii=False))


def cmd_session_new(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    session_id = db.create_session(args.title, topic_id=args.topic)
    print(json.dumps({
        "session_id": session_id,
        "title": args.title,
        "topic_id": (db.session(session_id) or {}).get("topic_id"),
    }, ensure_ascii=False))


def cmd_sessions(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    print(json.dumps(db.sessions(topic_id=args.topic), ensure_ascii=False))


def cmd_topics(_: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    print(json.dumps(db.topics(), ensure_ascii=False))


def cmd_topic_new(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    topic_id = db.create_topic(args.name, args.description)
    print(json.dumps({"topic_id": topic_id, "name": args.name}, ensure_ascii=False))


def cmd_topic_rename(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    if not db.rename_topic(args.topic, args.name):
        raise SystemExit(f"Topic {args.topic} not found.")
    print(json.dumps({"topic_id": args.topic, "name": args.name}, ensure_ascii=False))


def cmd_topic_delete(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    if not db.delete_topic(args.topic):
        raise SystemExit(f"Topic {args.topic} not found.")
    print(json.dumps({"topic_id": args.topic, "deleted": True}, ensure_ascii=False))


def cmd_history(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    if not db.session(args.session):
        raise SystemExit(f"Session {args.session} not found.")
    print(json.dumps(db.messages(args.session), ensure_ascii=False))


def cmd_session_fork(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    fork_id = db.fork_session(args.session)
    print(json.dumps({"session_id": fork_id, "forked_from": args.session}))


def cmd_session_delete(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    if not db.delete_session(args.session):
        raise SystemExit(f"Session {args.session} not found.")
    remove_session_export(args.session)
    print(json.dumps({"session_id": args.session, "deleted": True}))


def cmd_transcribe(args: argparse.Namespace) -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY before transcribing audio.")
    audio_path = Path(args.file).expanduser().resolve()
    if not audio_path.is_file():
        raise SystemExit(f"Audio file not found: {audio_path}")
    from openai import OpenAI

    client = OpenAI()
    with audio_path.open("rb") as audio_file:
        result = client.audio.transcriptions.create(
            model=os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-transcribe"),
            file=audio_file,
            prompt=(
                "A multilingual learning conversation. Preserve technical terms, product names, "
                "acronyms, code identifiers, and proper nouns exactly when possible."
            ),
        )
    print(json.dumps({"text": result.text}, ensure_ascii=False))


def cmd_status(_: argparse.Namespace) -> None:
    db = store()
    profile = require_profile(db)
    print("PROFILE")
    print(json.dumps(profile, ensure_ascii=False, indent=2))
    print("\nTASKS")
    print(json.dumps(db.tasks(limit=20), ensure_ascii=False, indent=2))
    print("\nEVIDENCE")
    print(json.dumps(db.evidence(limit=20), ensure_ascii=False, indent=2))


def cmd_calendar(args: argparse.Namespace) -> None:
    events = list_events(args.days)
    print(json.dumps(events, ensure_ascii=False, indent=2))


def cmd_schedule(args: argparse.Namespace) -> None:
    db = store()
    require_profile(db)
    tasks = {task["id"]: task for task in db.tasks(limit=100)}
    task = tasks.get(args.task_id)
    if not task:
        raise SystemExit(f"Task {args.task_id} not found.")
    start = datetime.fromisoformat(args.start)
    duration = args.duration or task["estimate_minutes"]
    print(
        f"Calendar event: {task['title']} | {start.astimezone().isoformat()} | "
        f"{duration} min | {args.calendar}"
    )
    if not args.yes:
        print("Preview only. Add --yes to create the event.")
        return
    create_event(task["title"], start, duration, args.calendar)
    print("Calendar event created.")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="study-agent")
    sub = root.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create or update the learner profile")
    init.add_argument(
        "--goal",
        default="",
    )
    init.add_argument("--deadline")
    init.add_argument("--weekly-hours", type=float, default=10)
    init.add_argument("--github", help="GitHub repository in owner/repo format")
    init.add_argument("--course", default="")
    init.add_argument("--progress", default="")
    init.set_defaults(func=cmd_init)

    today = sub.add_parser("today", help="Generate and persist today's plan")
    today.add_argument("--minutes", type=int, default=90)
    today.add_argument("--progress", default="")
    today.add_argument("--note", default="")
    today.set_defaults(func=cmd_today)

    review = sub.add_parser("review", help="Run an evening review")
    review.add_argument("--completed", default="")
    review.add_argument("--blocked", default="")
    review.add_argument("--evidence", default="")
    review.add_argument("--tomorrow-minutes", type=int, default=90)
    review.set_defaults(func=cmd_review)

    weekly = sub.add_parser("weekly", help="Run the weekly portfolio review")
    weekly.add_argument("--note", default="")
    weekly.set_defaults(func=cmd_weekly)

    chat = sub.add_parser("chat", help="Talk to the agent with persistent context")
    chat.add_argument("message")
    chat.add_argument("--session", type=int)
    chat.add_argument("--topic", type=int)
    chat.add_argument("--json", action="store_true")
    chat.set_defaults(func=cmd_chat)

    chat_context = sub.add_parser(
        "chat-context", help="Prepare local context for ChatGPT-plan inference"
    )
    chat_context.add_argument("message")
    chat_context.add_argument("--session", type=int)
    chat_context.add_argument("--topic", type=int)
    chat_context.set_defaults(func=cmd_chat_context)

    chat_save = sub.add_parser(
        "chat-save", help="Persist a completed externally generated chat turn"
    )
    chat_save.add_argument("--session", type=int, required=True)
    chat_save.add_argument("--user", required=True)
    chat_save.add_argument("--assistant", required=True)
    chat_save.set_defaults(func=cmd_chat_save)

    profile_update = sub.add_parser(
        "profile-update", help="Apply user-confirmed long-term profile changes"
    )
    profile_update.add_argument("--changes-json", required=True)
    profile_update.add_argument("--session", type=int)
    profile_update.set_defaults(func=cmd_profile_update)

    auth_status = sub.add_parser("auth-status", help="Show configured auth methods")
    auth_status.set_defaults(func=cmd_auth_status)

    clock = sub.add_parser("system-time", help="Read the local system clock as JSON")
    clock.set_defaults(func=cmd_system_time)

    insights_context = sub.add_parser(
        "insights-context", help="Prepare data for the Insights analysis"
    )
    insights_context.set_defaults(func=cmd_insights_context)

    insights_current = sub.add_parser(
        "insights-current", help="Show the latest saved Insights snapshot"
    )
    insights_current.set_defaults(func=cmd_insights_current)

    insights_save = sub.add_parser(
        "insights-save", help="Save an Insights JSON snapshot"
    )
    insights_save.add_argument("--file", required=True)
    insights_save.set_defaults(func=cmd_insights_save)

    insights_generate = sub.add_parser(
        "insights-generate", help="Generate Insights using API-key mode"
    )
    insights_generate.set_defaults(func=cmd_insights_generate)

    knowledge_path_parser = sub.add_parser(
        "knowledge-path", help="Show the portable knowledge directory"
    )
    knowledge_path_parser.set_defaults(func=cmd_knowledge_path)

    data_export = sub.add_parser(
        "data-export", help="Export agent state and knowledge as one portable bundle"
    )
    data_export.add_argument("--source", required=True)
    data_export.add_argument("--output", required=True)
    data_export.set_defaults(func=cmd_data_export)

    data_import = sub.add_parser(
        "data-import", help="Import a portable data bundle with an automatic backup"
    )
    data_import.add_argument("--file", required=True)
    data_import.set_defaults(func=cmd_data_import)

    session_new = sub.add_parser("session-new", help="Create a new chat session")
    session_new.add_argument("--title", default="New Chat")
    session_new.add_argument("--topic", type=int)
    session_new.set_defaults(func=cmd_session_new)

    sessions = sub.add_parser("sessions", help="List saved chat sessions as JSON")
    sessions.add_argument("--topic", type=int)
    sessions.set_defaults(func=cmd_sessions)

    topics = sub.add_parser("topics", help="List topics as JSON")
    topics.set_defaults(func=cmd_topics)

    topic_new = sub.add_parser("topic-new", help="Create a topic")
    topic_new.add_argument("--name", required=True)
    topic_new.add_argument("--description", default="")
    topic_new.set_defaults(func=cmd_topic_new)

    topic_rename = sub.add_parser("topic-rename", help="Rename a topic")
    topic_rename.add_argument("--topic", type=int, required=True)
    topic_rename.add_argument("--name", required=True)
    topic_rename.set_defaults(func=cmd_topic_rename)

    topic_delete = sub.add_parser("topic-delete", help="Delete a topic and move its sessions to General")
    topic_delete.add_argument("--topic", type=int, required=True)
    topic_delete.set_defaults(func=cmd_topic_delete)

    history = sub.add_parser("history", help="Show one session's messages as JSON")
    history.add_argument("--session", type=int, required=True)
    history.set_defaults(func=cmd_history)

    session_fork = sub.add_parser("session-fork", help="Fork a saved chat session")
    session_fork.add_argument("--session", type=int, required=True)
    session_fork.set_defaults(func=cmd_session_fork)

    session_delete = sub.add_parser("session-delete", help="Delete a saved chat session")
    session_delete.add_argument("--session", type=int, required=True)
    session_delete.set_defaults(func=cmd_session_delete)

    transcribe = sub.add_parser("transcribe", help="Transcribe a recorded audio file")
    transcribe.add_argument("--file", required=True)
    transcribe.set_defaults(func=cmd_transcribe)

    status = sub.add_parser("status", help="Show local state without an API call")
    status.set_defaults(func=cmd_status)

    cal = sub.add_parser("calendar", help="Read upcoming macOS Calendar events")
    cal.add_argument("--days", type=int, default=7)
    cal.set_defaults(func=cmd_calendar)

    schedule = sub.add_parser("schedule", help="Preview or create a Calendar event")
    schedule.add_argument("--task-id", type=int, required=True)
    schedule.add_argument(
        "--start", required=True, help="Local ISO datetime, e.g. 2026-11-07T19:00"
    )
    schedule.add_argument("--duration", type=int)
    schedule.add_argument("--calendar", default="Home")
    schedule.add_argument("--yes", action="store_true")
    schedule.set_defaults(func=cmd_schedule)
    return root


def main() -> None:
    load_env()
    args = parser().parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        raise SystemExit(130)
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

