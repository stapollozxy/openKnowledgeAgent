# Open Knowledge Agent Backend

The Python backend stores topics, sessions, tasks, evidence, and insights locally. It can run from Terminal or VS Code and is also used by the desktop app.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

For API-key mode, edit `.env` locally:

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=
OPENAI_TRANSCRIBE_MODEL=
GITHUB_TOKEN=
STUDY_AGENT_HOME=.study-agent
```

Do not commit `.env`, `.study-agent/`, or `knowledge/`.

## Initialize and use

```bash
study-agent init --goal "Your goal" --weekly-hours 5
study-agent topic-new --name "Your topic"
study-agent chat "Help me make a learning plan"
study-agent status
```

Use `study-agent --help` to see all commands for planning, review, topics, sessions, insights, GitHub, Calendar, and knowledge export.

## Storage

- SQLite state defaults to `.study-agent/agent.db`; override with `STUDY_AGENT_HOME`.
- Markdown exports default to `knowledge/`; override with `STUDY_AGENT_KNOWLEDGE_HOME`.
- The repository contains no prebuilt database or user data.
- A blank local profile is created automatically on first use, so ChatGPT sign-in can start a conversation without running `init` first.

The generated knowledge directory contains a portable README, insight snapshots, a question notebook, a learning roadmap, project ideas, a Mermaid knowledge graph, and session Markdown files.

## Safety boundaries

- GitHub data access in the agent backend is read-only.
- Calendar reads are available to the agent; event creation requires an explicit CLI `--yes` confirmation.
- Claims and project evidence should be based on stored user evidence, not invented metrics.

## Test

```bash
pytest
```
