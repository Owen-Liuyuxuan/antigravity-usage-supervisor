# Antigravity Usage Supervisor

[![CI](https://github.com/Owen-Liuyuxuan/antigravity-usage-supervisor/actions/workflows/ci.yml/badge.svg)](https://github.com/Owen-Liuyuxuan/antigravity-usage-supervisor/actions/workflows/ci.yml)

A privacy-focused GNOME Shell addon for Ubuntu 22.04+ that places current Google
Antigravity / Google AI Pro allowance (**Gemini 5-hour**, **Claude & GPT 5-hour**,
and **Claude & GPT 7-day** rolling windows) and local activity metrics in the top
panel. Modeled after
[`codex-usage-supervisor`](https://github.com/Owen-Liuyuxuan/codex-usage-supervisor),
the interface uses open space, clean typography, slim progress lines, and
frameless activity rows instead of boxed cards.

## Features & Components

- **GNOME Shell extension (`antigravity-usage-supervisor@owen.local`):**
  - Compact top-panel core indicator displaying the **Gemini 5-hour allowance**: `AGY 2.7%`
  - Clean dropdown popover showing all three quota limits with dedicated progress bars and exact reset countdowns:
    1. **5-hour allowance (Gemini)** (hero bar)
    2. **5-hour allowance (Claude & GPT)**
    3. **7-day allowance (Claude & GPT)**
    along with active model (`Gemini 4 Argon (Medium)`, etc.), signed-in account, today's tasks/focus/tokens, and recent conversations;
- **D-Bus service (`io.github.owen.AntigravityUsageSupervisor`):**
  - Queries live Google AI Pro quota buckets (`daily-cloudcode-pa.googleapis.com` / `cloudcode-pa.googleapis.com`) and parses local `~/.gemini/antigravity-cli` session telemetry away from the GNOME Shell UI process;
- **Libadwaita preferences & detail view (`antigravity-usage-supervisor-preferences`):**
  - Native GTK4/Libadwaita window displaying all three live quota bars (`Gemini 5h`, `Claude & GPT 5h`, `Claude & GPT 7d`) alongside personal daily token/focus-time goals and refresh interval;
- **Debian package & user installer:**
  - Installs and connects all components via `.deb` package or rootless user-space script.

See the [usage guide](docs/USAGE.md), [architecture](docs/ARCHITECTURE.md), and
[Google AI Pro quota investigation](docs/QUOTA_INVESTIGATION.md) for details.

---

## How Quota & Activity Monitoring Works

1. **Live Google AI Pro Quota Buckets (`● ACCOUNT`):**
   - Reads the locally authenticated Antigravity OAuth credentials from GNOME Keyring (`org.freedesktop.secrets`, `service="gemini", username="antigravity"`) or `~/.config/antigravity/plugin-secrets.json`, automatically refreshing expired access tokens in-memory.
   - Queries `v1internal:loadCodeAssist`, `v1internal:retrieveUserQuota`, and `v1internal:retrieveUserQuotaSummary` across both Cloud Code Assist endpoints to obtain:
     - **Plan tier:** `Google AI Pro` (`g1-pro-tier`)
     - **Primary (Core) bar:** **5-hour allowance (Gemini)** (`300` min window) with sub-percent precision and reset countdown
     - **Secondary bar:** **5-hour allowance (Claude & GPT)** (`300` min window) with reset countdown
     - **Tertiary bar:** **7-day allowance (Claude & GPT)** (`10,080` min weekly window) with reset countdown
   - Falls back to the local `language_server_linux_x64` Connect-RPC (`GetUserStatus`) or cached network limits (`~/.cache/antigravity-usage-supervisor/`) when offline.
2. **Local Session, Token & Focus Telemetry (`~/.gemini/antigravity-cli`):**
   - Scans `brain/*/.system_generated/logs/transcript.jsonl`, `conversation_summaries.db`, `annotations/*.pbtxt`, and `cli.log`.
   - Aggregates per-step `input_tokens`, `cache_read_tokens`, and `output_tokens`, rolls child subagent token consumption into parent conversations, and merges concurrent step timestamps to estimate daily focus time without double-counting.
   - Never retains or transmits prompt or response text.

---

## Installing on Another Ubuntu Machine

### 1. Prerequisites

Ensure the target Ubuntu machine (Ubuntu 22.04 LTS or newer with GNOME Shell 42–44) has:

1. **Google Antigravity (`agy` CLI or Antigravity IDE)** installed and signed in with your Google AI Pro account (`agy auth login` or signed in via the IDE so credentials exist in GNOME Keyring or `~/.config/antigravity/plugin-secrets.json`).
2. **System packages for building and running the extension:**
   ```bash
   sudo apt update
   sudo apt install -y git dpkg-dev python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gnome-shell-extension-prefs
   ```

### 2. Clone the Repository

```bash
git clone https://github.com/Owen-Liuyuxuan/antigravity-usage-supervisor.git
cd antigravity-usage-supervisor
```

### 3. Choose an Installation Method

#### Option A: Debian Package (`.deb`) — Recommended

Building and installing the `.deb` package registers the Python module, D-Bus service, systemd user unit, desktop launcher, and GNOME Shell extension system-wide:

```bash
./packaging/build_deb.sh
sudo apt install ./dist/antigravity-usage-supervisor_0.1.0_all.deb
systemctl --user daemon-reload
systemctl --user restart antigravity-usage-supervisor.service
```

#### Option B: Rootless User-Space Install (No `sudo` required)

If you do not have `sudo` privileges on the target Ubuntu machine (assuming `python3-gi`, `gir1.2-gtk-4.0`, and `gir1.2-adw-1` are already installed), install directly into `~/.local` and `~/.config`:

```bash
./packaging/install_user.sh
```

### 4. Activate the GNOME Shell Extension

GNOME Shell must discover the newly installed extension before it can be enabled:

- **On X11 / Xorg:** Press `Alt+F2`, type `r`, and press `Enter` to reload GNOME Shell in-place (or log out and back in).
- **On Wayland:** Log out of your desktop session and sign in again.

Then enable the extension:

```bash
gnome-extensions enable antigravity-usage-supervisor@owen.local
```

The `AGY <pct>%` indicator (reporting the Gemini 5-hour limit) will immediately appear in the top-right panel.

> **Note on GNOME Shell Versions:** `extension/metadata.json` lists GNOME Shell `42`, `43`, and `44` (Ubuntu 22.04–23.04). If installing on Ubuntu 23.10 or 24.04+ (GNOME Shell `45`/`46`) or if GNOME Shell reports a version mismatch, disable version validation with:
> ```bash
> gsettings set org.gnome.shell disable-extension-version-validation true
> ```

### 5. Verify & Configure on the New Machine

Check that the background D-Bus service can read your account quota and local telemetry:

```bash
gdbus call --session \
  --dest io.github.owen.AntigravityUsageSupervisor \
  --object-path /io/github/owen/AntigravityUsageSupervisor \
  --method io.github.owen.AntigravityUsageSupervisor.GetSummary
```

Open the preferences window from the GNOME app launcher (**Antigravity Usage Supervisor**) or run:

```bash
antigravity-usage-supervisor-preferences
```

---

## Upgrading an Existing Installation

After pulling new changes on any machine, rebuild/reinstall and restart the user service so the running D-Bus daemon picks up the updated backend code:

```bash
git pull
./packaging/build_deb.sh
sudo apt install --reinstall ./dist/antigravity-usage-supervisor_0.1.0_all.deb
systemctl --user daemon-reload
systemctl --user restart antigravity-usage-supervisor.service
```

---

## Development & Testing

Run one service snapshot in the terminal:

```bash
PYTHONPATH=src python3 -m antigravity_usage_supervisor.service --once
```

Launch the preferences UI directly from source:

```bash
PYTHONPATH=src python3 -m antigravity_usage_supervisor.preferences
```

Run the test suite and packaging checks:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --check extension/extension.js
./packaging/build_deb.sh
```

---

## Uninstall

### If installed via `.deb`:

```bash
gnome-extensions disable antigravity-usage-supervisor@owen.local
systemctl --user stop antigravity-usage-supervisor.service
sudo apt remove antigravity-usage-supervisor
```

### If installed via `install_user.sh`:

```bash
gnome-extensions disable antigravity-usage-supervisor@owen.local
systemctl --user stop antigravity-usage-supervisor.service
rm -rf ~/.local/share/gnome-shell/extensions/antigravity-usage-supervisor@owen.local \
       ~/.local/bin/antigravity-usage-supervisor* \
       ~/.local/share/dbus-1/services/io.github.owen.AntigravityUsageSupervisor.service \
       ~/.config/systemd/user/antigravity-usage-supervisor.service \
       ~/.local/share/applications/antigravity-usage-supervisor.desktop
systemctl --user daemon-reload
```

Personal settings remain in `~/.config/antigravity-usage-supervisor/settings.json`
unless removed manually.
