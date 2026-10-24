/* exported init */

'use strict';

const { Clutter, Gio, GLib, GObject, St } = imports.gi;
const Main = imports.ui.main;
const PanelMenu = imports.ui.panelMenu;
const PopupMenu = imports.ui.popupMenu;

const BUS_NAME = 'io.github.owen.AntigravityUsageSupervisor';
const OBJECT_PATH = '/io/github/owen/AntigravityUsageSupervisor';

const DBUS_XML = `
<node>
  <interface name="${BUS_NAME}">
    <method name="GetSummary">
      <arg name="summary" type="s" direction="out"/>
    </method>
    <method name="Refresh">
      <arg name="summary" type="s" direction="out"/>
    </method>
    <signal name="UsageChanged">
      <arg name="summary" type="s"/>
    </signal>
  </interface>
</node>`;

const UsageProxy = Gio.DBusProxy.makeProxyWrapper(DBUS_XML);

function compactNumber(value) {
    const number = Number(value || 0);
    if (number >= 1000000)
        return `${(number / 1000000).toFixed(1)}M`;
    if (number >= 1000)
        return `${(number / 1000).toFixed(0)}K`;
    return `${number}`;
}

function formatPercent(value) {
    const num = Number(value || 0);
    if (!Number.isFinite(num))
        return '0%';
    return `${Number(num.toFixed(2))}%`;
}

function windowName(windowObj) {
    if (!windowObj)
        return 'Antigravity allowance';
    if (windowObj.label)
        return windowObj.label;
    const minutes = windowObj.window_minutes;
    if (minutes && minutes % 1440 === 0)
        return `${minutes / 1440}-day allowance`;
    if (minutes && minutes % 60 === 0)
        return `${minutes / 60}-hour allowance`;
    return 'Antigravity allowance';
}

function resetText(value) {
    if (!value)
        return 'Reset time unavailable';
    const target = new Date(value);
    if (Number.isNaN(target.getTime()))
        return 'Reset time unavailable';
    const minutes = Math.max(0, Math.ceil((target.getTime() - Date.now()) / 60000));
    if (minutes < 60)
        return `Resets in ${minutes} min`;
    if (minutes < 1440)
        return `Resets in ${Math.floor(minutes / 60)}h ${minutes % 60}m`;
    return `Resets in ${Math.floor(minutes / 1440)}d ${Math.floor((minutes % 1440) / 60)}h`;
}

function relativeTime(value) {
    if (!value)
        return '';
    const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
    if (seconds < 60)
        return 'now';
    if (seconds < 3600)
        return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400)
        return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
}

class ProgressLine {
    constructor(accentClass) {
        this.actor = new St.Widget({ style_class: 'agy-progress-track' });
        this._fill = new St.Widget({ style_class: `agy-progress-fill ${accentClass}` });
        this.actor.add_child(this._fill);
        this.setFraction(0);
    }

    setFraction(value) {
        const fraction = Math.min(1, Math.max(0, Number(value) || 0));
        this._fill.set_width(Math.round(320 * fraction));
    }
}

const AntigravityIndicator = GObject.registerClass(
class AntigravityIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'Antigravity Usage Supervisor', false);

        const panelBox = new St.BoxLayout({ style_class: 'agy-panel-box' });
        this._panelIcon = new St.Icon({
            icon_name: 'starred-symbolic',
            style_class: 'system-status-icon agy-panel-icon',
        });
        this._panelLabel = new St.Label({
            text: 'G4 —',
            y_align: Clutter.ActorAlign.CENTER,
        });
        panelBox.add_child(this._panelIcon);
        panelBox.add_child(this._panelLabel);
        this.add_child(panelBox);

        this._buildPopover();
        this._connectService();
    }

    _buildPopover() {
        const item = new PopupMenu.PopupBaseMenuItem({ reactive: false, can_focus: false });
        const body = new St.BoxLayout({ vertical: true, style_class: 'agy-popover' });
        item.add_child(body);

        const header = new St.BoxLayout({ style_class: 'agy-header' });
        this._wordmarkLabel = new St.Label({
            text: 'ANTIGRAVITY · PRO',
            style_class: 'agy-wordmark',
            x_expand: true,
        });
        header.add_child(this._wordmarkLabel);
        this._liveLabel = new St.Label({ text: '● LOCAL', style_class: 'agy-live' });
        header.add_child(this._liveLabel);
        body.add_child(header);

        this._primaryValue = new St.Label({ text: '—', style_class: 'agy-hero-value' });
        body.add_child(this._primaryValue);
        this._primaryCaption = new St.Label({
            text: 'Waiting for Google AI Pro usage data',
            style_class: 'agy-caption',
        });
        body.add_child(this._primaryCaption);
        this._primaryBar = new ProgressLine('agy-progress-primary');
        body.add_child(this._primaryBar.actor);
        this._modelMeta = new St.Label({ text: '', style_class: 'agy-model-meta' });
        body.add_child(this._modelMeta);

        body.add_child(new St.Widget({ style_class: 'agy-divider' }));
        body.add_child(new St.Label({ text: 'TODAY', style_class: 'agy-section-label' }));
        const stats = new St.BoxLayout({ style_class: 'agy-stats' });
        [
            ['tasks', 'TASKS'],
            ['focus', 'FOCUS'],
            ['tokens', 'TOKENS'],
        ].forEach(([key, label]) => {
            const column = new St.BoxLayout({ vertical: true, style_class: 'agy-stat', x_expand: true });
            this[`_${key}Value`] = new St.Label({ text: '—', style_class: 'agy-stat-value' });
            column.add_child(this[`_${key}Value`]);
            column.add_child(new St.Label({ text: label, style_class: 'agy-stat-label' }));
            stats.add_child(column);
        });
        body.add_child(stats);

        body.add_child(new St.Widget({ style_class: 'agy-divider' }));
        body.add_child(new St.Label({ text: 'RECENT ACTIVITY', style_class: 'agy-section-label' }));
        this._recentBox = new St.BoxLayout({ vertical: true, style_class: 'agy-recent-list' });
        body.add_child(this._recentBox);

        this.menu.addMenuItem(item);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        const refresh = new PopupMenu.PopupMenuItem('Refresh now');
        refresh.connect('activate', () => this._requestRefresh());
        this.menu.addMenuItem(refresh);
        const preferences = new PopupMenu.PopupMenuItem('Details & Preferences');
        preferences.connect('activate', () => this._openPreferences());
        this.menu.addMenuItem(preferences);
    }

    _connectService() {
        this._proxy = new UsageProxy(
            Gio.DBus.session,
            BUS_NAME,
            OBJECT_PATH,
            (proxy, error) => {
                if (error) {
                    this._showError('Service unavailable');
                    return;
                }
                this._signalId = proxy.connectSignal('UsageChanged', (_proxy, _sender, [summary]) => {
                    this._applySummary(summary);
                });
                proxy.GetSummaryRemote((result, callError) => {
                    if (callError)
                        this._showError('Could not read usage');
                    else
                        this._applySummary(result[0]);
                });
            }
        );
    }

    _applySummary(serialized) {
        let summary;
        try {
            summary = JSON.parse(serialized);
        } catch (_error) {
            this._showError('Invalid service response');
            return;
        }
        if (summary.error) {
            this._showError(summary.error);
            return;
        }

        const limits = summary.rate_limits || {};
        const planName = (limits.plan_type || 'PRO').toUpperCase();
        this._wordmarkLabel.text = planName.includes('ANTIGRAVITY')
            ? planName
            : `ANTIGRAVITY · ${planName}`;

        const groups = limits.groups || [];
        const argonGroup = groups.find(g => g.group_id === 'gemini_argon');
        // Keep the panel pinned to Argon even when another model is active.
        const heroWindow = limits.gemini_argon_weekly || (argonGroup && argonGroup.weekly)
            || (limits.primary && limits.primary.bucket_id === 'gemini-argon-wtu-weekly'
                ? limits.primary : null);

        if (heroWindow) {
            const usedNum = Number(heroWindow.used_percent || 0);
            const remNum = heroWindow.remaining_percent !== undefined
                ? Number(heroWindow.remaining_percent)
                : Math.max(0, 100 - usedNum);
            const pctUsed = formatPercent(usedNum);
            const pctLeft = formatPercent(remNum);
            this._panelLabel.text = `G4 ${pctLeft} left`;
            this._primaryValue.text = `${pctLeft} left`;
            this._primaryCaption.text = `${windowName(heroWindow)}  ·  ${pctUsed} used  ·  ${resetText(heroWindow.resets_at)}`;
            this._primaryBar.setFraction(remNum / 100);
            this._setUrgency(usedNum);
        } else {
            this._panelLabel.text = 'G4 —';
            this._primaryValue.text = 'Argon quota unavailable';
            this._primaryCaption.text = 'Check Antigravity sign-in or refresh';
            this._primaryBar.setFraction(0);
            this._setUrgency(0);
        }

        const activeModel = summary.active_model || limits.active_model || '';
        const email = summary.account_email || limits.account_email || '';
        const metaParts = [activeModel, email].filter(Boolean);
        this._modelMeta.text = metaParts.join('  ·  ');

        const today = summary.today || {};
        this._tasksValue.text = `${today.sessions || 0}`;
        this._focusValue.text = `${today.focus_minutes || 0} min`;
        this._tokensValue.text = compactNumber(today.tokens);
        this._renderRecent(summary.recent || []);

        if (summary.rate_limits_source === 'cloudcode-api') {
            this._liveLabel.text = '● ACCOUNT';
            this._liveLabel.remove_style_class_name('agy-stale');
        } else {
            this._liveLabel.text = summary.rate_limits_source === 'network-cache'
                ? '● NETWORK CACHE'
                : '● LOCAL CACHE';
            this._liveLabel.add_style_class_name('agy-stale');
        }
        this._liveLabel.remove_style_class_name('agy-error');
    }

    _renderRecent(items) {
        this._recentBox.get_children().forEach(child => child.destroy());
        if (!items.length) {
            this._recentBox.add_child(new St.Label({ text: 'No recent tasks', style_class: 'agy-empty' }));
            return;
        }
        items.slice(0, 3).forEach(item => {
            const row = new St.BoxLayout({ style_class: 'agy-recent-row' });
            const isRunning = (item.status || '').includes('RUNNING');
            const dot = new St.Label({
                text: '●',
                style_class: isRunning ? 'agy-activity-dot agy-activity-running' : 'agy-activity-dot',
            });
            row.add_child(dot);
            const text = new St.BoxLayout({ vertical: true, x_expand: true });
            text.add_child(new St.Label({
                text: item.name || 'Untitled task',
                style_class: 'agy-task-name',
                x_align: Clutter.ActorAlign.START,
            }));
            const metaParts = [
                item.project,
                item.model,
                item.tokens ? `${compactNumber(item.tokens)} tok` : '',
            ].filter(Boolean);
            text.add_child(new St.Label({
                text: metaParts.join(' · '),
                style_class: 'agy-task-meta',
                x_align: Clutter.ActorAlign.START,
            }));
            row.add_child(text);
            row.add_child(new St.Label({
                text: isRunning ? 'active' : relativeTime(item.updated_at),
                style_class: 'agy-task-time',
            }));
            this._recentBox.add_child(row);
        });
    }

    _setUrgency(percent) {
        this._panelLabel.remove_style_class_name('agy-warning');
        this._panelLabel.remove_style_class_name('agy-critical');
        if (percent >= 95)
            this._panelLabel.add_style_class_name('agy-critical');
        else if (percent >= 80)
            this._panelLabel.add_style_class_name('agy-warning');
    }

    _requestRefresh() {
        if (!this._proxy)
            return;
        this._liveLabel.text = '● REFRESHING';
        this._proxy.RefreshRemote((result, error) => {
            if (error)
                this._showError('Refresh failed');
            else
                this._applySummary(result[0]);
        });
    }

    _openPreferences() {
        try {
            Gio.Subprocess.new(
                ['antigravity-usage-supervisor-preferences'],
                Gio.SubprocessFlags.NONE
            );
        } catch (error) {
            Main.notifyError('Antigravity Usage Supervisor', `Could not open preferences: ${error.message}`);
        }
    }

    _showError(message) {
        this._panelLabel.text = 'G4 !';
        this._liveLabel.text = '● OFFLINE';
        this._liveLabel.add_style_class_name('agy-error');
        this._primaryValue.text = 'Unavailable';
        this._primaryCaption.text = message;
    }

    destroy() {
        if (this._proxy && this._signalId)
            this._proxy.disconnectSignal(this._signalId);
        this._proxy = null;
        super.destroy();
    }
});

class Extension {
    enable() {
        this._indicator = new AntigravityIndicator();
        Main.panel.addToStatusArea('antigravity-usage-supervisor', this._indicator);
    }

    disable() {
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }
}

function init() {
    return new Extension();
}
