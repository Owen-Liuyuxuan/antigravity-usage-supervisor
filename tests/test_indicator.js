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
    'modelMeta', 'tasksValue', 'focusValue', 'tokensValue', 'liveLabel', 'sharedCaption', 'sharedReset']) {
    indicator['_' + name] = {text: '', add_style_class_name() {}, remove_style_class_name() {}};
}
indicator._primaryBar = {setFraction(value) { this.fraction = value; }};
indicator._sharedBar = {setFraction(value) { this.fraction = value; }};
indicator._renderRecent = () => {};
const summary = {
    rate_limits_source: 'cloudcode-api', active_model: 'Claude Sonnet',
    rate_limits: {
        primary: {bucket_id: '3p-5h', used_percent: 0},
        gemini_argon_weekly: {bucket_id: 'gemini-argon-wtu-weekly',
            used_percent: 99.19, remaining_percent: 0.81},
        gemini_weekly: {bucket_id: 'gemini-weekly', used_percent: 10, remaining_percent: 90},
        gemini_5h: {bucket_id: 'gemini-5h', used_percent: 1.5, remaining_percent: 98.5},
    },
};
indicator._applySummary(JSON.stringify(summary));
assert.equal(indicator._panelLabel.text, 'A 99.19% · G 1.5%');
assert.equal(indicator._sharedBar.fraction, 0.9);
assert.match(indicator._sharedCaption.text, /Neon \/ Hydrogen \/ Flash \/ Pro/);
assert.equal(indicator._primaryValue.text, '0.81% left');
assert.ok(Math.abs(indicator._primaryBar.fraction - 0.0081) < 1e-12);
delete summary.rate_limits.gemini_argon_weekly;
indicator._applySummary(JSON.stringify(summary));
assert.equal(indicator._panelLabel.text, 'A — · G 1.5%');
assert.equal(indicator._primaryValue.text, 'Argon quota unavailable');
assert.equal(indicator._primaryBar.fraction, 0);
delete summary.rate_limits.gemini_5h;
indicator._applySummary(JSON.stringify(summary));
assert.equal(indicator._panelLabel.text, 'A — · G —');
assert.equal(indicator._sharedBar.fraction, 0.9);
delete summary.rate_limits.gemini_weekly;
indicator._applySummary(JSON.stringify(summary));
assert.equal(indicator._panelLabel.text, 'A — · G —');
assert.equal(indicator._sharedBar.fraction, 0);
indicator._showError('offline');
assert.equal(indicator._panelLabel.text, 'A — · G —');
assert.equal(indicator._sharedBar.fraction, 0);
console.log('Indicator: separate Argon/shared Gemini quotas, precision, and missing-quota handling passed');
