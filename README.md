# Open Knowledge Agent

A local-first learning and knowledge agent with a macOS desktop UI and a terminal backend.

The repository ships with no user profile, chat history, database, credentials, configured repository, knowledge files, or machine-specific paths. New users create their own topics and sessions after installation.

## Features

- Organize conversations by topic and session.
- Continue, fork, copy, and delete sessions.
- Save course, course progress, and goals to the local long-term profile only after explicit in-app confirmation.
- Use ChatGPT sign-in or an OpenAI API key.
- Connect GitHub through the GitHub CLI.
- Use macOS speech recognition for voice prompts.
- Generate learning insights, questions, roadmaps, projects, and a Markdown knowledge graph.
- Choose the top-level folder for portable knowledge exports.
- Export an existing agent database and knowledge directory as one `.okagent` file, then import it on another installation with an automatic local backup.
- Read local system time and optionally integrate with macOS Calendar.

## Quick start

### Backend

```bash
cd study-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
study-agent init
```

Leave `.env` blank when using ChatGPT sign-in in the desktop app. For API-key mode, add your own `OPENAI_API_KEY` locally. Never commit `.env`.

### Desktop app

Install the GitHub CLI if GitHub sign-in is needed:

```bash
brew install gh
```

Build the macOS app:

```bash
cd desktop-app
chmod +x build_app.sh
./build_app.sh
```

The result is `desktop-app/dist/Open Knowledge Agent.app`. It includes the local state backend, so ChatGPT sign-in works without selecting another folder. In Settings, an external `study-agent` directory with `.venv` is optional and is only needed for API-key Agents SDK mode.

## Local data and privacy

Runtime data is intentionally excluded from Git:

- `.env`: API credentials and local configuration.
- `.study-agent/agent.db`: profiles, topics, sessions, messages, tasks, and insights.
- `knowledge/`: exported Markdown knowledge.
- Electron configuration and encrypted ChatGPT credentials: stored by macOS in the app's user-data directory and Keychain.
- GitHub credentials: managed by the GitHub CLI and macOS credential storage.

The app does not include a preconfigured account or personal learning data. Review generated knowledge files before publishing them: they are designed to contain the user's own conversations and learning history.

Portable `.okagent` bundles intentionally contain user learning data, but never `.env`, API keys, ChatGPT/GitHub credentials, application configuration, caches, or virtual environments. Treat exported bundles as private files.

## Development

```bash
cd study-agent
pytest

cd ../desktop-app
npm install
npm start
```

See [study-agent/README.md](study-agent/README.md) and [desktop-app/README.md](desktop-app/README.md) for component details.

## VS Code Codex

Open this repository as the VS Code workspace and start a Codex chat. Ask to enter **Open Knowledge Agent mode** or make a learning/course/topic request. The project `AGENTS.md` routes Codex to `./scripts/oka`, which shares the macOS app's local profile, topics, sessions, tasks, evidence, and knowledge without copying ChatGPT credentials or requiring an API key.

The first shared-data command may ask Codex for read/write permission to `~/Library/Application Support/Open Knowledge Agent`. Approve that precise directory to let VS Code and the desktop app use the same local state.

```bash
./scripts/oka status
./scripts/oka topics
./scripts/oka --help
```

Profile changes still require explicit confirmation. Set `OPEN_KNOWLEDGE_AGENT_APP_SUPPORT` or the more specific data/knowledge environment variables documented in `docs/codex-agent.md` when using a non-default data location.

## Third-party component

The bundled Sign in with ChatGPT devkit has its own noncommercial license inside `desktop-app/vendor/siwc-local-0.1.0.tgz`. Review that license before redistributing or using this project commercially.
