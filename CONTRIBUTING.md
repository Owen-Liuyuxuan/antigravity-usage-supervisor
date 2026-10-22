# Contributing

Thank you for improving Antigravity Usage Supervisor. The project targets Ubuntu
22.04+ with GNOME Shell 42–44 and Python 3.10+.

## Development setup

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

## Change guidelines

- Keep prompt and response bodies out of the D-Bus contract.
- Never store OAuth credentials in the repository, logs, D-Bus payloads, or settings JSON.
- Keep filesystem parsing and network polling outside the GNOME Shell process.
- Add tests for changes to quota parsing, session aggregation, or serialization behavior.
- Support the shell versions declared in `extension/metadata.json`.

Submit focused changes with a clear description, verification evidence, and
screenshots for visible UI changes.
