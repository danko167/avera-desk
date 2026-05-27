# Avera Desk Backend

FastAPI backend for Avera Desk desktop app. It provides REST APIs, a WebSocket channel, OAuth state handling for Microsoft 365 and Gmail, background workers, and realtime speech command processing.

Monorepo note:

- Use ../README.md as the primary repo-level guide.

## Tech Stack

- Python 3.11+
- FastAPI + Uvicorn
- SQLAlchemy async + SQLite (aiosqlite)
- httpx
- MSAL (Microsoft OAuth)
- keyring when available, with in-process session fallback for secrets

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Run

Recommended during development:

```powershell
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Alternative entrypoint:

```powershell
python main.py
```

Notes:

- main.py reads AVERA_DESK_HOST and AVERA_DESK_PORT.
- In packaged/production profile, non-loopback host binding is refused.

## Test

```powershell
python -m pytest
```

## Runtime Responsibilities

- Maintains app settings and OAuth setup state.
- Runs background workers via lifespan startup.
- Serves /health and /api routes.
- Accepts WebSocket clients at /ws and pushes realtime updates.
- Handles push-to-talk transcription pipeline.
- Tracks aggregated LLM usage totals for UI reporting.

## OAuth Provider Behavior (Current)

- Active provider is selected by email_provider setting (m365 or gmail).
- GET /api/oauth/login-url resolves provider from settings and returns provider-specific login URL.
- Callback routes are provider-specific:
  - Microsoft: /api/oauth/callback
  - Gmail: /api/oauth/google/callback
- Both callback routes support GET query callbacks and POST form_post callbacks.
- GET /api/oauth/status reports authenticated, persistence, setup_required, and missing_settings.
- Optional query param resolve_mailbox=true enables connected mailbox lookup on demand.
- setup_required includes both OAuth config gaps and missing AI key requirements:
  - speech_api_key required when speech_provider is openai or openrouter
  - llm_api_key required when llm_provider is openai or openrouter

## Current REST API Surface

Health:

- GET /health

Settings and conversation:

- GET /api/settings
- PUT /api/settings
- POST /api/settings/test-ai-connection
- POST /api/settings/clear-ai-secrets
- GET /api/settings/llm-usage-summary
- GET /api/conversation-turns

Local auth bootstrap:

- GET /api/local-auth/token
- POST /api/local-auth/ws-ticket

Local auth bootstrap semantics:

- /api/local-auth/token requires loopback client origin checks.
- /api/local-auth/ws-ticket returns ticket and expires_in_seconds=45.

OAuth:

- GET /api/oauth/login-url
- GET /api/oauth/callback
- POST /api/oauth/callback
- GET /api/oauth/google/callback
- POST /api/oauth/google/callback
- GET /api/oauth/status
- POST /api/oauth/logout

OAuth callback responses:

- Callback endpoints return short HTML pages indicating success/failure and auto-close the popup.
- GET /api/oauth/login-url can return HTTP 400 with detail code oauth_setup_required and missing_settings array.

Email and follow-ups:

- GET /api/emails/recent
- POST /api/emails/sync
- GET /api/emails/sync-status
- GET /api/followups
- GET /api/followups/{follow_up_id}

Drafts:

- GET /api/email-drafts/{draft_id}
- PATCH /api/email-drafts/{draft_id}
- POST /api/email-drafts/{draft_id}/send
- POST /api/email-drafts/{draft_id}/cancel

Calendar:

- GET /api/calendar/events/upcoming
- POST /api/calendar/availability
- POST /api/calendar-proposals/plan
- GET /api/calendar-proposals
- POST /api/calendar-proposals
- GET /api/calendar-proposals/{proposal_id}
- PATCH /api/calendar-proposals/{proposal_id}
- POST /api/calendar-proposals/{proposal_id}/approve
- POST /api/calendar-proposals/{proposal_id}/reject
- POST /api/calendar-proposals/{proposal_id}/cancel

## Current WebSocket Contract

Endpoint:

- WS /ws

Incoming message types accepted by ws router:

- ping
- set_status
- mock_trigger
- dismiss_notification
- text_command
- audio_start
- audio_blob
- audio_stop

Outgoing messages sent by backend:

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

Realtime safety limits currently enforced server-side:

- max single audio chunk size: 256 KB
- max base64 chars per chunk: 1,400,000
- max accumulated bytes per audio session: 10 MB

## Settings Model (AppSettings)

Stored and served fields include:

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

Update payload also supports optional gmail_client_secret, speech_api_key, and llm_api_key.

Defaults from settings service:

- m365_redirect_url defaults to http://localhost:8000/api/oauth/callback
- gmail_redirect_url defaults to http://localhost:8000/api/oauth/google/callback

## Local Desktop Security Model

- Backend is intended for loopback-only desktop usage.
- HTTP API (except bootstrap/callback paths) requires x-avera-local-token.
- WebSocket clients require a short-lived ws_ticket query parameter.
- Allowed origins are validated against local desktop defaults (override via AVERA_ALLOWED_ORIGINS).
- Public AI base URLs in /api/settings/test-ai-connection are blocked by default unless AVERA_ALLOW_PUBLIC_AI_TEST_BASE_URL=1.
- ws_ticket is consumed once and cannot be reused.
- Local auth bootstrap endpoints additionally require loopback client origin checks.

Auth exemptions in HTTP middleware:

- /health
- /api/local-auth/token
- /api/oauth/callback
- /api/oauth/google/callback

Important toggles:

- AVERA_DISABLE_LOCAL_AUTH=1 disables local auth checks (not recommended outside test/dev).
- AVERA_PERSIST_LOCAL_AUTH_TOKEN controls dev token persistence behavior.
- AVERA_ALLOW_PUBLIC_AI_TEST_BASE_URL=1 allows public hostnames for AI connection tests.
- AVERA_ALLOWED_ORIGINS can override allowed CORS/WebSocket origins.

Token persistence behavior:

- Default in development: local auth token is persisted to disk to survive reloads.
- Default in packaged runtime: local auth token is process-local unless explicitly configured otherwise.

## Secrets and Persistence

- Secrets are written to keyring if available.
- If keyring is unavailable/fails, values fall back to in-memory session storage.
- OAuth status persistence reflects this as none, session, or persistent.

## Configuration Notes

- SQLite DB is initialized by app/db startup logic.
- OAuth provider is selected from email_provider setting.
- API keys are retrieved from secure storage conventions in services.
- Transcription trace can be toggled through settings.

Provider-specific required OAuth settings:

- m365: m365_client_id, m365_tenant_id, m365_redirect_url
- gmail: gmail_client_id, gmail_client_secret, gmail_redirect_url

Environment fallback (when not loaded from DB settings):

- m365: M365_CLIENT_ID, M365_TENANT_ID, M365_REDIRECT_URL
- gmail: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REDIRECT_URL

URL guardrails in settings update and AI connection testing:

- base URLs are normalized as HTTP/HTTPS URLs
- external providers (OpenAI/OpenRouter) require https:// for public hosts
- non-private hosts are blocked unless explicitly allowed by environment toggle

OAuth scopes currently requested:

- m365 Graph scopes: Mail.Read, Mail.Send, People.Read, Calendars.Read, Calendars.ReadWrite, User.Read
- Gmail scopes: gmail.readonly, gmail.send, userinfo.email

Calendar limitation:

- Calendar endpoints currently reject non-m365 providers with HTTP 400.

Microsoft OAuth account support depends on app registration:

- Supported account types in Entra must include personal accounts for Outlook.com/Hotmail/Live sign-in.
- m365_tenant_id can be tenant UUID/domain or one of common, organizations, consumers.
- m365_redirect_url must exactly match configured Redirect URI.

Gmail OAuth support depends on Google Cloud OAuth credentials:

- Authorized redirect URI must exactly match gmail_redirect_url.
- Client secret must be configured (settings payload or GMAIL_CLIENT_SECRET env var).

## Scope Note

This README documents backend behavior and backend contracts. Renderer/UI usage details are documented in ../frontend/README.md.

## Frontend Integration Notes

- frontend/scripts/dev-api.mjs runs this backend with reload on 127.0.0.1:8000.
- frontend/scripts/build-backend.mjs packages backend as one-file executable and stages it as frontend/src-tauri/resources/backend/avera-backend.bin.

## Troubleshooting

### Backend startup fails

- Confirm venv is active and requirements are installed.
- Confirm port 8000 is free.

### OAuth setup_required stays true

- Check required provider settings in /api/settings.
- Confirm required API keys are configured.

### WebSocket connects but no updates

- Verify frontend sends supported message types.
- Verify ws_ticket is present and fresh.
- Check backend logs for ws_message_received and protocol_error events.

### Speech command pipeline errors

- Validate speech_model and speech_base_url settings.
- Ensure speech API key is configured for selected provider.

## License

See LICENSE.
