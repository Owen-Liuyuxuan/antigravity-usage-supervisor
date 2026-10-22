# Security and privacy

## Data boundaries

Antigravity Usage Supervisor reads local session metadata and numeric counters
from `~/.gemini/antigravity-cli`. It does not retain or transmit prompt or
response text.

To retrieve live Google AI Pro quota buckets (`5-hour` and `7-day` allowances),
the background D-Bus service reads the locally authenticated Antigravity OAuth
token from GNOME Keyring (`org.freedesktop.secrets`, `service="gemini",
username="antigravity"`) or `~/.config/antigravity/plugin-secrets.json` and
queries Google's Cloud Code Assist quota endpoints (`loadCodeAssist`,
`retrieveUserQuota`, and `retrieveUserQuotaSummary`).

Security guarantees:

- Credentials are read strictly from the desktop secret service or Antigravity's
  own local secret store and refreshed only in-memory;
- Credentials are never written to settings JSON, cache files, logs, or D-Bus;
- Task names and workspace paths remain on the local desktop and are exposed
  only on the user's session D-Bus (`io.github.owen.AntigravityUsageSupervisor`).

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's security advisory
feature rather than opening a public issue containing sensitive details.
