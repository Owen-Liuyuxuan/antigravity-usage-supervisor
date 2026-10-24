// Exercise the real render method without requiring a running GNOME Shell.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const context = {
    imports: {
        gi: {Gio: {DBusProxy: {makeProxyWrapper: () => null}},
            GObject: {registerClass: klass => klass}},
        ui: {main: {}, panelMenu: {Button: class {}}, popupMenu: {}},
    },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('extension/extension.js', 'utf8') +
    '\nglobalThis.Indicator = AntigravityIndicator;', context);
const indicator = Object.create(context.Indicator.prototype);
for (const name of ['wordmarkLabel', 'panelLabel', 'primaryValue', 'primaryCaption',
    'modelMeta', 'tasksValue', 'focusValue', 'tokensValue', 'liveLabel']) {
    indicator['_' + name] = {text: '', add_style_class_name() {}, remove_style_class_name() {}};
}
indicator._primaryBar = {setFraction(value) { this.fraction = value; }};
indicator._renderRecent = () => {};
const summary = {
    rate_limits_source: 'cloudcode-api', active_model: 'Claude Sonnet',
    rate_limits: {
        primary: {bucket_id: '3p-5h', used_percent: 0},
        gemini_argon_weekly: {bucket_id: 'gemini-argon-wtu-weekly',
            used_percent: 99.19, remaining_percent: 0.81},
    },
};
indicator._applySummary(JSON.stringify(summary));
assert.equal(indicator._panelLabel.text, 'G4 0.81% left');
assert.equal(indicator._primaryValue.text, '0.81% left');
assert.ok(Math.abs(indicator._primaryBar.fraction - 0.0081) < 1e-12);
delete summary.rate_limits.gemini_argon_weekly;
indicator._applySummary(JSON.stringify(summary));
assert.equal(indicator._panelLabel.text, 'G4 —');
assert.equal(indicator._primaryValue.text, 'Argon quota unavailable');
assert.equal(indicator._primaryBar.fraction, 0);
console.log('Indicator: Argon priority, precision, and missing-quota handling passed');
