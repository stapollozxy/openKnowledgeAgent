# VS Code Codex learning-agent workflow

Use this workflow only for learning, planning, knowledge, or interview-coaching requests. The macOS app and Codex share the same SQLite database and knowledge directory through `./scripts/oka`.

On first use, request read/write access only to `~/Library/Application Support/Open Knowledge Agent`. This permission lets Codex share the app database; it does not expose ChatGPT or GitHub credentials from Keychain.

1. Read `BASE_INSTRUCTIONS` in `study-agent/src/study_agent/agent.py`. Run `./scripts/oka system-time`, `./scripts/oka status`, and `./scripts/oka topics`. The context is ready when current time, profile, tasks, evidence, and topics are known.
2. Resolve the topic and session. Use `./scripts/oka sessions --topic ID` and `./scripts/oka history --session ID`. Continue the user's named session; otherwise use the most relevant recent session or create one with `session-new` when the request clearly starts a new thread.
3. Coach with repository and terminal tools as useful. Persist concrete tasks with `task-new`, verified completion with `task-complete`, and real artifacts or results with `evidence-add`.
4. Treat `course`, `course_progress`, and `goal` as confirmed memory. Before `profile-update`, show old → new values and obtain explicit user confirmation in the current Codex chat. A successful command is the completion criterion.
5. When operating in a persistent session, save the completed exchange with `chat-save` so the desktop app can continue it. The saved assistant text must match the answer given to the user.

Run `./scripts/oka --help` for the command surface. The wrapper accepts `OPEN_KNOWLEDGE_AGENT_APP_SUPPORT`, `OPEN_KNOWLEDGE_AGENT_DATA_HOME`, and `OPEN_KNOWLEDGE_AGENT_KNOWLEDGE_HOME` overrides for non-default installations.
