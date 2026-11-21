# Contributing

Antigravity Usage Supervisor supports Ubuntu 22.04+ with GNOME Shell 42–44
and Windows x64 and ARM64. Both platforms use Python 3.10 or later.

## Repository layout

| Path | Responsibility |
| --- | --- |
| `src/antigravity_usage_supervisor/` | Shared usage parsing, quota querying, settings, and snapshot format. `service.py` provides the GNOME D-Bus entry point and `windows_backend.py` provides Windows JSON IPC. |
| `extension/` and `packaging/*.sh` | GNOME panel and Ubuntu installation. |
| `windows/` and `packaging/windows/` | Windows WPF tray application and installation. |

Develop both platforms on `main` through short-lived feature branches. For
changes to the shared backend, verify the snapshot contract for both clients.
The CI workflow runs Ubuntu and Windows checks on pushes and pull requests.

## Ubuntu development

The core parser has no third-party Python dependencies. Desktop integration
uses the distribution packages for PyGObject, GTK4, and Libadwaita:

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gnome-shell shellcheck desktop-file-utils
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --check extension/extension.js
shellcheck packaging/build_deb.sh packaging/install_user.sh
```

Build the Debian package with `./packaging/build_deb.sh`. For extension testing,
install the build, restart the user service and GNOME Shell, and watch the user
journal:

```bash
journalctl --user -f -o cat | grep -i antigravity
```

## Windows development

With Python 3.10+ and .NET 10 installed, run the shared tests and build the
tray project from the repository root.

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -v
dotnet build windows/AntigravityUsageSupervisor -c Release
```

See the [Windows guide](docs/WINDOWS.md) for local installation and testing
the tray against an authenticated agy session.

## Releases

Use one Git tag per release, with the version in `pyproject.toml` matching
the tag. Build the Ubuntu `.deb` from that tag. Windows users can run the
PowerShell installer from the same tagged source. The Windows CI job
validates self-contained builds for x64 and ARM64.

## Change guidelines

- Keep prompt and response bodies out of the desktop snapshot.
- Never store OAuth credentials in the repository, logs, IPC payloads, or settings JSON.
- Keep filesystem parsing and network polling outside the desktop UI processes.
- Add tests for changes to quota parsing, session aggregation, or serialization behavior.
- Support the shell versions declared in `extension/metadata.json`.

Submit focused changes with a clear description, verification evidence, and
screenshots for visible UI changes.
