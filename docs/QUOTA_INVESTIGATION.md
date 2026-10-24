# Google AI Pro Individual Quota Investigation for Antigravity

## 1. How Antigravity Tracks Quota for Google AI Pro Individual Accounts

Antigravity (`agy` CLI and Antigravity IDE) authenticates individual Google AI Pro
users via consumer OAuth (`auth_method: "consumer"`) and maps the account to tier
`g1-pro-tier` (`Google AI Pro`) under companion project `aicode-consumers`.

Live verification on 2026-10-24 found **three model groups and five windows**
for this Google AI Pro account:

1. **Gemini Models:** `gemini-weekly` and `gemini-5h`, shared by Flash and Pro.
2. **Claude and GPT models:** `3p-weekly` and `3p-5h`.
3. **Gemini 4 Argon:** separate `gemini-argon-wtu-weekly` on paid Pro.
   The server describes Ultra as including higher Argon quota in the larger
   Gemini quota bucket; do not assume this account's layout applies to all tiers.

The verified snapshot reported **0.81% remaining for Argon** and **98.75%
remaining for Gemini Models weekly**. These are distinct allowances. The panel
is pinned to Argon; all five windows appear in Details.

`retrieveUserQuotaSummary` supplies explicit group/window identifiers and takes
precedence. Per-model data is a fallback for absent families. A weekly limit
cannot be inferred from how many hours remain before its reset.

Each bucket reports:
- `remainingFraction` (`float` in `[0.0, 1.0]`, where `used_percent = (1.0 - remainingFraction) * 100`)
- `resetTime` (ISO-8601 UTC timestamp when the window resets)

---

## 2. Comparison of Quota Retrieval Methods on Ubuntu

During investigation on this system, three candidate mechanisms were analyzed and tested:

### Method A: Direct Cloud Code Assist Quota API via Keyring OAuth Token (Selected Primary)
- **Where Credentials Live:**
  - `agy` stores the OAuth token bundle in **GNOME Keyring** (`org.freedesktop.secrets`) under attributes `service="gemini", username="antigravity"` (with fallback to `~/.config/antigravity/plugin-secrets.json`).
  - Contains `token.access_token`, `token.refresh_token`, `token.expiry`, and `id_token` (JWT containing the user's `email` and `aud` OAuth `client_id`).
- **Endpoints Polled:**
  1. `POST https://daily-cloudcode-pa.googleapis.com/v1internal:loadCodeAssist`
     - Returns `paidTier: {"id": "g1-pro-tier", "name": "Google AI Pro"}` and `cloudaicompanionProject: "aicode-consumers"`.
  2. `POST https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota`
     - Returns high-precision per-model `remainingFraction` (e.g. `0.977231` -> `2.3% used`) and `resetTime` reflecting real-time `agy` CLI usage.
  3. `POST https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary` (and `cloudcode-pa`)
     - Returns all five explicit buckets across Gemini Models, Claude and GPT models, and Gemini 4 Argon.
- **Why It Is Most Reliable:**
  - Works whether the Antigravity IDE or `agy` CLI is currently running or closed.
  - When `agy` is closed and `access_token` expires after 1 hour, `account.py` refreshes the token in-memory using `refresh_token` against `https://oauth2.googleapis.com/token`.
  - Captures sub-percent quota consumption immediately.

### Method B: Local `language_server_linux_x64` Connect-RPC (`GetUserStatus`) (Selected Secondary Fallback)
- **How It Works:**
  - Antigravity IDE spawns `language_server_linux_x64 --csrf_token <uuid> --random_port`.
  - Exposes `POST http://127.0.0.1:<port>/exa.language_server_pb.LanguageServerService/GetUserStatus` with header `x-codeium-csrf-token: <uuid>`.
- **Important Caveat Discovered on This System:**
  - The installed Antigravity IDE (`v1.104.0`, built Nov 2025) bundles a localhost TLS certificate (`/usr/share/antigravity/resources/app/extensions/antigravity/dist/languageServer/cert.pem`) that expired on `2026-09-04T20:55:04Z`.
  - Because the system clock is past `2026-09-04`, the IDE extension host fails its TLS handshake (`ConnectError: [internal] certificate has expired`) and never forwards the user's OAuth token to `language_server_linux_x64`, leaving the local language server unauthenticated (`You are not logged into Antigravity`).
  - Meanwhile, `agy` CLI runs its own language server in-process with an in-memory CSRF token not exposed on the command line.
  - Therefore, relying solely on `language_server_linux_x64` would fail on this machine, whereas Method A succeeds 100% of the time.

### Method C: Local Session Transcripts & SQLite Summary Store (Always-On Local Telemetry)
- **Where Local Telemetry Lives:**
  - `~/.gemini/antigravity-cli/brain/<conversation-id>/.system_generated/logs/transcript.jsonl` records every `USER_INPUT` and `PLANNER_RESPONSE` step with exact `created_at` timestamps and incremental `input_tokens`, `cache_read_tokens`, and `output_tokens`.
  - `~/.gemini/antigravity-cli/conversation_summaries.db` records conversation titles, workspaces (`workspace_uris`), run status (`CASCADE_RUN_STATUS_RUNNING` / `IDLE`), and parent-child subagent links (`parent_conversation_id`).
  - `~/.gemini/antigravity-cli/annotations/<conversation-id>.pbtxt` stores human-readable conversation titles.
  - `~/.gemini/antigravity-cli/cli.log` records the authenticated email and active model override (`Propagating selected model override to backend: label="Gemini 4 Argon (Medium)"`).
