# Open Knowledge Agent Desktop

Electron-based macOS UI for the local Python backend.

The app starts as an always-on-top floating widget. Expand it to browse topics and sessions, continue a conversation, fork/copy/delete sessions, use voice prompts, connect accounts, and generate knowledge exports.

## Prerequisites

- macOS on Apple Silicon
- Node.js and npm
- The macOS system Python for the bundled local state backend
- Optional: `brew install gh` for GitHub sign-in

## Run in development

```bash
npm install
npm start
```

## Build

```bash
chmod +x build_app.sh
./build_app.sh
```

The build output is `dist/Open Knowledge Agent.app`. The app is ad-hoc signed for local use.

ChatGPT sign-in uses the bundled local state backend, so a user can sign in and start directly. Settings can optionally select an external backend directory with `.venv` and `.env` for API-key Agents SDK mode. ChatGPT sign-in credentials are encrypted with macOS Keychain; no credential is included in this repository.

## Input and portability

- Chinese and other IME composition is protected from accidental Enter-to-send behavior.
- Long-term profile changes are shown as a before/after proposal and are written locally only after **Confirm & save**.
- Paste PNG, JPEG, or WebP screenshots into the composer. The app previews them and uses local macOS Vision text recognition before sending the extracted text with the prompt. Images are not added to the data bundle.
- The compact widget has a dedicated drag handle and remembers its last position.
- **Export Data** creates one `.okagent` file containing the active SQLite database and portable Markdown knowledge. It excludes `.env`, API keys, login sessions, application configuration, caches, and virtual environments.
- **Import Data** restores that bundle and automatically backs up the receiving app's current database and knowledge before replacement.
