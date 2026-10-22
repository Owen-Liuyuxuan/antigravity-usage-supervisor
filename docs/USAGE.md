# Usage Guide

## Where the visualization lives

The application launcher (**Antigravity Usage Supervisor**) opens the Libadwaita
detail & preferences window showing all three quota limits (**Gemini 5h**,
**Claude & GPT 5h**, and **Claude & GPT 7d**) and configuration settings. The
core top-panel visualization is the `AGY <percent>%` indicator in the upper-right
GNOME panel, which reports the **Gemini 5-hour allowance**.

After installing the package or running `./packaging/install_user.sh`, enable
the extension:

```bash
gnome-extensions enable antigravity-usage-supervisor@owen.local
```

On X11, if GNOME Shell has not yet discovered the newly installed extension,
press `Alt+F2`, type `r`, and press Enter before enabling it. On Wayland, log
out and sign in again.

When upgrading an existing installation, reload and restart the user service:

```bash
systemctl --user daemon-reload
systemctl --user restart antigravity-usage-supervisor.service
```

Click the `AGY` panel indicator (which reports the core Gemini 5-hour limit) to see:

- **5-hour allowance (Gemini)** hero usage bar and reset countdown;
- active model name (e.g. `Gemini 4 Argon (Medium)`) and signed-in Google AI Pro account;
- **5-hour allowance (Claude & GPT)** usage bar and reset countdown;
- **7-day allowance (Claude & GPT)** usage bar and reset countdown;
- today's tasks, estimated focus time, and local token count (including subagents);
- the three most recently active Antigravity conversations (`active` indicator when running).

## Diagnostics

Check the extension state:

```bash
gnome-extensions info antigravity-usage-supervisor@owen.local
```

Request a backend snapshot over D-Bus:

```bash
gdbus call --session \
  --dest io.github.owen.AntigravityUsageSupervisor \
  --object-path /io/github/owen/AntigravityUsageSupervisor \
  --method io.github.owen.AntigravityUsageSupervisor.GetSummary
```

Inspect service status:

```bash
systemctl --user status antigravity-usage-supervisor.service
```
