#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
local_bin="${HOME}/.local/bin"
ext_dir="${HOME}/.local/share/gnome-shell/extensions/antigravity-usage-supervisor@owen.local"
dbus_dir="${HOME}/.local/share/dbus-1/services"
systemd_dir="${HOME}/.config/systemd/user"
apps_dir="${HOME}/.local/share/applications"
icons_dir="${HOME}/.local/share/icons/hicolor/scalable/apps"

install -d "${local_bin}" "${ext_dir}" "${dbus_dir}" "${systemd_dir}" "${apps_dir}" "${icons_dir}"

cat > "${local_bin}/antigravity-usage-supervisor-service" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="${project_dir}/src\${PYTHONPATH:+:\${PYTHONPATH}}"
exec python3 -m antigravity_usage_supervisor.service "\$@"
EOF
chmod 0755 "${local_bin}/antigravity-usage-supervisor-service"

cat > "${local_bin}/antigravity-usage-supervisor-preferences" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="${project_dir}/src\${PYTHONPATH:+:\${PYTHONPATH}}"
exec python3 -m antigravity_usage_supervisor.preferences "\$@"
EOF
chmod 0755 "${local_bin}/antigravity-usage-supervisor-preferences"
ln -sf "${local_bin}/antigravity-usage-supervisor-preferences" "${local_bin}/antigravity-usage-supervisor"

install -m 0644 "${project_dir}"/extension/* "${ext_dir}/"
install -m 0644 "${project_dir}/packaging/antigravity-usage-supervisor.svg" "${icons_dir}/"

sed "s|Exec=antigravity-usage-supervisor-preferences|Exec=${local_bin}/antigravity-usage-supervisor-preferences|" \
  "${project_dir}/packaging/antigravity-usage-supervisor.desktop" > "${apps_dir}/antigravity-usage-supervisor.desktop"

cat > "${dbus_dir}/io.github.owen.AntigravityUsageSupervisor.service" <<EOF
[D-BUS Service]
Name=io.github.owen.AntigravityUsageSupervisor
Exec=${local_bin}/antigravity-usage-supervisor-service
SystemdService=antigravity-usage-supervisor.service
EOF

cat > "${systemd_dir}/antigravity-usage-supervisor.service" <<EOF
[Unit]
Description=Local Google Antigravity usage metrics service

[Service]
Type=dbus
BusName=io.github.owen.AntigravityUsageSupervisor
ExecStart=${local_bin}/antigravity-usage-supervisor-service
Restart=on-failure
RestartSec=2
EOF

systemctl --user daemon-reload || true
systemctl --user restart antigravity-usage-supervisor.service || true
gnome-extensions enable antigravity-usage-supervisor@owen.local 2>/dev/null || true

echo "Installed user-level Antigravity Usage Supervisor service and GNOME extension."
