# Usage Guide

## Where the visualization lives

The top-panel indicator displays **Gemini 4 Argon weekly quota remaining**, for
example `G4 0.81% left`. It stays focused on Argon when other models are selected.
The launcher opens a **Details** tab containing all five quota windows, plus a
separate **Settings** tab. Percentages retain two decimal places where needed.
Missing Argon quota displays `G4 —` rather than substituting another quota.

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

Click the `G4` panel indicator to see:

- **Gemini 4 Argon weekly** remaining quota, used percentage, and reset countdown;
- active model and signed-in account;
- today's tasks, estimated focus time, local tokens, and recent conversations;
- **Details & Preferences**, opening all five quota windows and settings.

The Details tab shows Argon weekly, Gemini Models weekly/five-hour, and
Claude & GPT weekly/five-hour. Each window has its own reset countdown. Below the quota rows, scroll to see
today's task count, estimated focus time, today's tokens, tokens over the last
seven days, quota data source, and recent tasks.

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
