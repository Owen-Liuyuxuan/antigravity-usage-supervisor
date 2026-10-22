# Changelog

## 0.1.0 (2026-10-22)

- Initial release of Antigravity Usage Supervisor for Ubuntu / GNOME Shell.
- Added live Google AI Pro quota polling via Cloud Code Assist API (`loadCodeAssist`, `retrieveUserQuota`, `retrieveUserQuotaSummary`) with GNOME Keyring OAuth credential discovery and in-memory token refresh.
- Added fallback to local `language_server_linux_x64` Connect-RPC (`GetUserStatus`) and atomic network cache (`~/.cache/antigravity-usage-supervisor/`).
- Added local session, subagent rollup, focus-time, and token telemetry parser for `~/.gemini/antigravity-cli`.
- Added GNOME Shell top-panel extension (reporting core Gemini 5-hour limit in the top bar and all three limits — Gemini 5h, Claude & GPT 5h, and Claude & GPT 7d — in the dropdown popover), D-Bus service, Libadwaita detail & preferences app, and `.deb` / user-space packaging.
