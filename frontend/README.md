# Avera Desk Frontend

Tauri v2 desktop UI for Avera Desk. It connects to the local FastAPI backend, displays notifications, and provides push-to-talk voice interaction.

Monorepo note:

- Use ../README.md as the primary repo-level guide.

## What It Does Today

- Desktop shell with custom title bar, tray integration, and multi-window routing.
- Push-to-talk voice input using Ctrl+Space global shortcut in Tauri.
- Real-time transcript display and command feedback from backend.
- Notification timeline with conversation history and token usage badges.
- Notification workflows for follow-ups, email drafts, and calendar proposals.
- Settings UI for email provider (Microsoft 365 or Gmail), AI providers, connection overrides, and UI mode toggles.
- Dedicated Manual window accessible from tray and title-bar action.

## Tech Stack

- Tauri v2 + Rust
- React 19 + TypeScript
- Mantine UI
- Vite 7
- WebSocket and REST client in src/lib/api.ts
- PCM16 worklet in public/pcm16-worklet.js

## Prerequisites

- Node.js 20+
- Rust toolchain (for Tauri)
- Python 3.11+ (backend runtime)
- Windows is the primary tested desktop target

## Scripts

From frontend:

```powershell
npm install
```
- npm run tauri dev: runs full desktop app (uses beforeDevCommand from src-tauri/tauri.conf.json).
- npm run tauri build: production desktop build (runs build:backend then build via beforeBuildCommand).
- npm run dev:ui: Vite UI only on port 1420.
- npm run dev:api: starts backend via ../backend with uvicorn reload.
- npm run dev:desktop: runs UI and API together with concurrently.
- npm run build: builds TypeScript + Vite web bundle.
- npm run build:backend: bundles backend sidecar binary into src-tauri/resources/backend/avera-backend.bin.
- npm run test: runs Vitest test suite once.
- npm run test:watch: runs Vitest in watch mode.

For most local development, run only:

```powershell
npm run tauri dev
```

This starts both frontend and backend for you.

## Runtime Behavior

- In dev, Tauri uses http://localhost:1420 as devUrl.
- Vite dev proxy currently forwards /ws and /health to backend at 127.0.0.1:8000.
- API base and WS URL are configurable in settings and persisted in localStorage.
- App bootstraps settings and OAuth status from backend on startup.
- App bootstraps local auth token and obtains short-lived ws_ticket values for WebSocket connections.
- Window labels currently used by renderer routing: main, startup, settings, manual.

Startup/bootstrap details:

- Startup waits for both settings and OAuth bootstrap before normal runtime UI unlocks.
- Bootstrap fetch retries are enabled in frontend startup logic (500ms delay, up to 30 attempts).
- local auth token is cached in localStorage client-side for reuse between sessions.
- ws_ticket is fetched via POST /api/local-auth/ws-ticket and then attached to WS connect URL.
- ws_ticket values are short-lived (45 seconds) and single-use server-side.

## OAuth Setup (Provider-Specific)

OAuth is provider-driven. The Connect flow always calls GET /api/oauth/login-url, and backend resolves provider from current email_provider setting.

Microsoft 365 (email_provider=m365):

- Required values in UI: m365_client_id, m365_tenant_id, m365_redirect_url.
- Common redirect value: http://localhost:8000/api/oauth/callback.
- Tenant can be UUID, tenant domain, or common/organizations/consumers.

Gmail (email_provider=gmail):

- Required values in UI: gmail_client_id, gmail_client_secret, gmail_redirect_url.
- Common redirect value: http://localhost:8000/api/oauth/google/callback.
- Gmail secret entry is write-only from UI; backend only returns gmail_client_secret_configured flag.

Popup callback routes are handled by backend and close automatically on success/failure:

- /api/oauth/callback (Microsoft)
- /api/oauth/google/callback (Gmail)
- Both callback URLs support GET and POST callbacks.

Current provider limitation:

- Calendar endpoints currently require m365 provider server-side.

## Tray Behavior

Release tray menu:

- Open Avera Desk
- Settings
- Open Manual
- disabled info rows for shortcut and app version
- Quit

Debug-only tray actions:

- Trigger attention
- Trigger calendar attention

## Current Settings Model

Frontend settings mirror backend AppSettings and include:

- enable_transcription_trace
- enable_text_input_mode
- email_sync_interval_minutes
- app_api_base_url
- app_ws_url
- email_provider (m365 or gmail)
- m365_client_id, m365_tenant_id, m365_redirect_url
- gmail_client_id, gmail_client_secret_configured, gmail_redirect_url
- speech_provider, speech_model, speech_base_url, speech_api_key_configured
- llm_provider, llm_model, llm_base_url, llm_api_key_configured

UI settings currently exposed:

- Email tab: provider selection, OAuth fields, sync interval, connect/disconnect
- AI tab: speech and LLM provider/model/base URL/API key configuration
- UI tab: enable_text_input_mode toggle
- Advanced tab: API base URL, WebSocket URL, transcription trace toggle

Source of defaults and storage parsing: src/lib/startup.ts

## REST Endpoints Used by Frontend

- GET /health
- GET /api/local-auth/token
- POST /api/local-auth/ws-ticket
- GET, PUT /api/settings
- POST /api/settings/test-ai-connection
- GET /api/settings/llm-usage-summary
- POST /api/settings/clear-ai-secrets
- GET /api/oauth/status
- GET /api/oauth/login-url
- POST /api/oauth/logout
- POST /api/emails/sync
- GET /api/emails/sync-status
- GET /api/conversation-turns
- GET /api/followups/{id}
- GET /api/email-drafts/{id}
- PATCH /api/email-drafts/{id}
- POST /api/email-drafts/{id}/send
- POST /api/email-drafts/{id}/cancel
- POST /api/calendar-proposals/plan
- GET /api/calendar-proposals/{id}
- PATCH /api/calendar-proposals/{id}
- POST /api/calendar-proposals/{id}/approve
- POST /api/calendar-proposals/{id}/reject
- POST /api/calendar-proposals/{id}/cancel
- GET /api/calendar/events/upcoming
- POST /api/calendar/availability

## WebSocket Contract

Outgoing from frontend:

- ping
- set_status
- mock_trigger
- dismiss_notification
- text_command
- audio_start
- audio_blob
- audio_stop

Incoming to frontend:

- snapshot
- status
- notification
- conversation_turn
- feedback_processing
- recognized_action
- transcript_partial
- transcript_final
- close_window_after
- protocol_error
- pong

## Troubleshooting

### Backend Not Reachable

- Run npm run dev:api (or npm run dev:desktop / npm run tauri dev).
- Verify backend is listening on 127.0.0.1:8000.
- Check app_api_base_url and app_ws_url in settings.

### 401 Or Bootstrap Failures During Dev

- Frontend auto-refreshes local auth token once when it sees token/auth failures.
- If the backend restarted, ws_ticket may be stale; reconnecting the app window forces a new ticket request.
- Ensure backend runs on loopback and origin is allowed by backend local security rules.

### Voice Input Not Working

- Confirm microphone permissions for the desktop app.
- Verify speech API key is configured in backend secure storage.
- Hold Ctrl+Space (or press and hold mic button) to capture audio.

### OAuth Setup Required

- Fill provider-specific fields in Email settings tab.
- For M365: client id, tenant id (or authority alias), redirect URL.
- For Gmail: client id, client secret, redirect URL.

For Microsoft accounts, account eligibility is decided by your Entra app registration.

## Scope Note

This README documents frontend behavior and frontend-used contracts. Backend-only routes and internals are documented in ../backend/README.md.

## License

See LICENSE.
