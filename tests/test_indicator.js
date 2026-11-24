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
    'secondaryName', 'secondaryValue', 'secondaryReset',
    'claudeName', 'claudeValue', 'claudeReset',
    'modelMeta', 'tasksValue', 'focusValue', 'tokensValue', 'liveLabel']) {
    indicator['_' + name] = {text: '', add_style_class_name() {}, remove_style_class_name() {}};
}
indicator._primaryBar = {setFraction(value) { this.fraction = value; }};
indicator._secondaryBar = {setFraction(value) { this.fraction = value; }};
indicator._claudeBar = {setFraction(value) { this.fraction = value; }};
indicator._renderRecent = () => {};

const summary = {
    rate_limits_source: 'cloudcode-api', active_model: 'Gemini 4 Carbon (High)',
    rate_limits: {
        primary: {bucket_id: 'gemini-5h', used_percent: 1.5, remaining_percent: 98.5},
        gemini_5h: {bucket_id: 'gemini-5h', used_percent: 1.5, remaining_percent: 98.5, label: '5-hour allowance (Gemini)'},
        gemini_weekly: {bucket_id: 'gemini-weekly', used_percent: 10, remaining_percent: 90, label: '7-day allowance (Gemini)'},
        claude_gpt_5h: {bucket_id: '3p-5h', used_percent: 0, remaining_percent: 100, label: '5-hour allowance (Claude & GPT)'},
        claude_gpt_weekly: {bucket_id: '3p-weekly', used_percent: 5, remaining_percent: 95, label: '7-day allowance (Claude & GPT)'},
    },
};
indicator._applySummary(JSON.stringify(summary));
assert.equal(indicator._panelLabel.text, 'G 1.5%');
assert.equal(indicator._primaryValue.text, '90% left');
assert.match(indicator._primaryCaption.text, /Neon \/ Carbon \/ Argon \/ Hydrogen \/ Flash \/ Pro/);
assert.match(indicator._primaryCaption.text, /7-day limit/);
assert.ok(Math.abs(indicator._primaryBar.fraction - 0.9) < 1e-12);
assert.equal(indicator._secondaryValue.text, '98.5% left');
assert.ok(Math.abs(indicator._secondaryBar.fraction - 0.985) < 1e-12);
assert.equal(indicator._claudeValue.text, '95% left');

// When 5-hour window is tighter, hero switches to 5-hour and secondary shows 7-day.
summary.rate_limits.gemini_5h.used_percent = 25;
summary.rate_limits.gemini_5h.remaining_percent = 75;
indicator._applySummary(JSON.stringify(summary));
assert.equal(indicator._panelLabel.text, 'G 25%');
assert.equal(indicator._primaryValue.text, '75% left');
assert.match(indicator._primaryCaption.text, /5-hour limit/);
assert.equal(indicator._secondaryValue.text, '90% left');

// Missing individual Gemini windows display '—' without substituting Claude.
delete summary.rate_limits.gemini_5h;
delete summary.rate_limits.primary;
indicator._applySummary(JSON.stringify(summary));
assert.equal(indicator._panelLabel.text, 'G —');
assert.equal(indicator._primaryValue.text, '90% left');
assert.equal(indicator._secondaryValue.text, '—');
assert.equal(indicator._secondaryBar.fraction, 0);

delete summary.rate_limits.gemini_weekly;
indicator._applySummary(JSON.stringify(summary));
assert.equal(indicator._panelLabel.text, 'G —');
assert.equal(indicator._primaryValue.text, 'Gemini quota unavailable');
assert.equal(indicator._primaryBar.fraction, 0);
assert.equal(indicator._claudeValue.text, '95% left');

indicator._showError('offline');
assert.equal(indicator._panelLabel.text, 'G —');
assert.equal(indicator._primaryBar.fraction, 0);
assert.equal(indicator._secondaryBar.fraction, 0);
assert.equal(indicator._claudeBar.fraction, 0);
console.log('Indicator: unified Gemini (Neon/Carbon/Argon/Hydrogen/Flash/Pro) and Claude/GPT handling passed');
