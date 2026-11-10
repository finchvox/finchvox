// Tests for ui/js/preferences.js, run with: node --test scripts/test_preferences.cjs
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, '../ui/js/preferences.js'), 'utf8');
const KEY = 'finchvox.preferences';

// Objects made inside the vm sandbox have the sandbox's prototypes, so compare
// plain copies.
const plain = value => JSON.parse(JSON.stringify(value));

class MemoryStorage {
    constructor(entries = {}) { this.map = new Map(Object.entries(entries)); }
    getItem(key) { return this.map.has(key) ? this.map.get(key) : null; }
    setItem(key, value) { this.map.set(key, String(value)); }
    removeItem(key) { this.map.delete(key); }
}

// A minimal browser: window with localStorage, events and computed styles,
// and a <html> element whose data attributes and inline style are recorded.
function loadPreferences({ storage = new MemoryStorage(), cssValues = {}, storageThrows = false } = {}) {
    const root = {
        dataset: {},
        inlineStyle: {},
        style: { setProperty(name, value) { root.inlineStyle[name] = value; } },
    };
    const window = new EventTarget();
    Object.defineProperty(window, 'localStorage', {
        get() {
            if (storageThrows) throw new Error('SecurityError: storage is blocked');
            return storage;
        },
    });
    window.document = { documentElement: root };
    window.getComputedStyle = () => ({ getPropertyValue: name => cssValues[name] ?? '' });
    window.CustomEvent = CustomEvent;
    const events = [];
    window.addEventListener('finchvox:preferences', event => events.push(event.detail));
    vm.runInNewContext(source, { window });
    return { prefs: window.FinchvoxPreferences, root, window, storage, events };
}

test('with nothing stored, the defaults apply to the page', () => {
    const { prefs, root } = loadPreferences();
    assert.deepEqual(plain(prefs.load()), {
        theme: 'insights', textSize: 'default', timeFormat: '12h', defaultView: 'conversation',
        showAllSpans: false, logLevels: { DEBUG: true, INFO: true, WARN: true, ERROR: true },
        slowReplySeconds: 2, inspectorWidth: 460,
    });
    assert.equal(root.dataset.palette, 'insights');
    assert.equal(root.inlineStyle['--text-scale'], '1');
});

test('stored preferences apply before the page is drawn', () => {
    const storage = new MemoryStorage({ [KEY]: JSON.stringify({ theme: 'classic', textSize: 'large' }) });
    const { root } = loadPreferences({ storage });
    assert.equal(root.dataset.palette, 'classic');
    assert.equal(root.inlineStyle['--text-scale'], '1.15');
});

test('unknown or malformed values fall back to their defaults', () => {
    const { prefs } = loadPreferences();
    const cleaned = prefs.sanitize({
        theme: 'neon', textSize: 'huge', timeFormat: 'metric', defaultView: 'settings',
        showAllSpans: 'yes', logLevels: { DEBUG: false, INFO: 'no', TRACE: false }, slowReplySeconds: 'soon',
    });
    assert.equal(cleaned.theme, 'insights');
    assert.equal(cleaned.textSize, 'default');
    assert.equal(cleaned.timeFormat, '12h');
    assert.equal(cleaned.defaultView, 'conversation');
    assert.equal(cleaned.showAllSpans, false);
    assert.deepEqual(plain(cleaned.logLevels), { DEBUG: false, INFO: true, WARN: true, ERROR: true });
    assert.equal(cleaned.slowReplySeconds, 2);
    assert.deepEqual(plain(prefs.sanitize(null)), plain(prefs.sanitize({})));
    assert.deepEqual(plain(prefs.sanitize([1, 2])), plain(prefs.sanitize({})));
});

test('the slow-reply threshold is kept within range and to one decimal', () => {
    const { prefs } = loadPreferences();
    assert.equal(prefs.sanitize({ slowReplySeconds: 0.1 }).slowReplySeconds, 0.5);
    assert.equal(prefs.sanitize({ slowReplySeconds: 99 }).slowReplySeconds, 30);
    assert.equal(prefs.sanitize({ slowReplySeconds: 2.46 }).slowReplySeconds, 2.5);
    assert.equal(prefs.sanitize({ slowReplySeconds: '3.2' }).slowReplySeconds, 3.2);
    assert.equal(prefs.sanitize({ slowReplySeconds: Infinity }).slowReplySeconds, 2);
});

test('saving merges, stores, applies and announces the change', () => {
    const { prefs, root, storage, events } = loadPreferences();
    prefs.save({ theme: 'classic' });
    const saved = prefs.save({ textSize: 'small', defaultView: 'trace' });

    assert.equal(saved.theme, 'classic');
    assert.equal(saved.defaultView, 'trace');
    assert.deepEqual(JSON.parse(storage.getItem(KEY)), plain(saved));
    assert.equal(root.dataset.palette, 'classic');
    assert.equal(root.inlineStyle['--text-scale'], '0.9');
    assert.equal(events.length, 2);
    assert.equal(events[1].textSize, 'small');
});

test('reset removes the stored preferences and restores the defaults', () => {
    const { prefs, root, storage, events } = loadPreferences();
    prefs.save({ theme: 'classic', textSize: 'large' });
    const defaults = prefs.reset();

    assert.equal(storage.getItem(KEY), null);
    assert.equal(defaults.theme, 'insights');
    assert.equal(root.dataset.palette, 'insights');
    assert.equal(root.inlineStyle['--text-scale'], '1');
    assert.equal(events.at(-1).theme, 'insights');
});

test('broken stored data does not break the page', () => {
    const storage = new MemoryStorage({ [KEY]: '{not json' });
    const { prefs, root } = loadPreferences({ storage });
    assert.equal(prefs.load().theme, 'insights');
    assert.equal(root.dataset.palette, 'insights');
});

test('blocked storage still lets preferences apply to the open page', () => {
    const { prefs, root } = loadPreferences({ storageThrows: true });
    assert.equal(prefs.load().theme, 'insights');
    const saved = prefs.save({ theme: 'classic' });
    assert.equal(saved.theme, 'classic');
    assert.equal(root.dataset.palette, 'classic');
});

test('a change made in another tab is applied here', () => {
    const { prefs, root, storage, window, events } = loadPreferences();
    storage.setItem(KEY, JSON.stringify({ theme: 'classic' }));
    window.dispatchEvent(Object.assign(new Event('storage'), { key: KEY }));
    assert.equal(root.dataset.palette, 'classic');
    assert.equal(events.at(-1).theme, 'classic');

    window.dispatchEvent(Object.assign(new Event('storage'), { key: 'something-else' }));
    assert.equal(events.length, 1);
    assert.equal(prefs.load().theme, 'classic');
});

test('theme values are read from the CSS variables, with a fallback', () => {
    const { prefs } = loadPreferences({ cssValues: { '--chart-llm': ' #ec4899 ' } });
    assert.equal(prefs.cssToken('--chart-llm', '#000000'), '#ec4899');
    assert.equal(prefs.cssToken('--missing', '#6b7280'), '#6b7280');
});

test('the inspector width is remembered within 320 to 900 pixels', () => {
    const { prefs } = loadPreferences();
    assert.equal(prefs.load().inspectorWidth, 460);
    assert.equal(prefs.sanitize({ inspectorWidth: 612.6 }).inspectorWidth, 613);
    assert.equal(prefs.sanitize({ inspectorWidth: 100 }).inspectorWidth, 320);
    assert.equal(prefs.sanitize({ inspectorWidth: 5000 }).inspectorWidth, 900);
    assert.equal(prefs.sanitize({ inspectorWidth: 'wide' }).inspectorWidth, 460);
    prefs.save({ inspectorWidth: 700 });
    assert.equal(prefs.load().inspectorWidth, 700);
});

test('time format and text scale helpers follow the saved preferences', () => {
    const { prefs } = loadPreferences();
    assert.equal(prefs.hour12(), true);
    assert.equal(prefs.textScale(), 1);
    prefs.save({ timeFormat: '24h', textSize: 'large' });
    assert.equal(prefs.hour12(), false);
    assert.equal(prefs.textScale(), 1.15);
});
