# Usage Guide

## Where the visualization lives

The application launcher opens **preferences only**. The live visualization is
the `AGY <percent>%` indicator in the upper-right GNOME panel.

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

Click the `AGY` panel indicator to see:

- current primary model group 5-hour allowance usage and reset countdown;
- active model name (e.g. `Gemini 4 Argon (Medium)`) and signed-in Google AI Pro account;
- secondary model group (`Claude & GPT 5-hour allowance`) and 7-day weekly limit status;
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
