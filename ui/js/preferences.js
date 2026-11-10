/* Finchvox display preferences, kept in this browser (localStorage).
 *
 * Loaded in <head> on every page, before the page is drawn, so the chosen
 * theme and text size apply without a flash of the defaults. Pages read the
 * rest (opening tab, log levels, time format, ...) through
 * window.FinchvoxPreferences and listen for CHANGE_EVENT to update live.
 *
 * Preferences are per browser and per address: a Finchvox on port 3100 and
 * one on port 3200 keep separate preferences.
 */
(function (global) {
    'use strict';

    const STORAGE_KEY = 'finchvox.preferences';
    const CHANGE_EVENT = 'finchvox:preferences';

    const THEMES = ['insights', 'classic'];
    const TEXT_SCALES = Object.freeze({ small: 0.9, default: 1, large: 1.15 });
    const TIME_FORMATS = ['12h', '24h'];
    const VIEWS = ['conversation', 'trace', 'logs', 'metrics'];
    const LOG_LEVELS = ['DEBUG', 'INFO', 'WARN', 'ERROR'];
    const SLOW_REPLY_RANGE = Object.freeze({ min: 0.5, max: 30 });
    // Width of the span and log inspectors, set by dragging their edge.
    const INSPECTOR_WIDTH_RANGE = Object.freeze({ min: 320, max: 900, default: 460 });

    const DEFAULTS = Object.freeze({
        theme: 'insights',
        textSize: 'default',
        timeFormat: '12h',
        defaultView: 'conversation',
        showAllSpans: false,
        logLevels: Object.freeze({ DEBUG: true, INFO: true, WARN: true, ERROR: true }),
        slowReplySeconds: 2,
        inspectorWidth: INSPECTOR_WIDTH_RANGE.default,
    });

    function oneOf(value, allowed, fallback) {
        return allowed.includes(value) ? value : fallback;
    }

    function slowReply(value) {
        const number = typeof value === 'string' ? Number(value) : value;
        if (typeof number !== 'number' || !Number.isFinite(number)) return DEFAULTS.slowReplySeconds;
        const clamped = Math.min(SLOW_REPLY_RANGE.max, Math.max(SLOW_REPLY_RANGE.min, number));
        return Math.round(clamped * 10) / 10;
    }

    function inspectorWidth(value) {
        if (typeof value !== 'number' || !Number.isFinite(value)) return INSPECTOR_WIDTH_RANGE.default;
        return Math.round(Math.min(INSPECTOR_WIDTH_RANGE.max, Math.max(INSPECTOR_WIDTH_RANGE.min, value)));
    }

    // Returns a complete, valid preferences object; anything unknown or
    // malformed falls back to its default.
    function sanitize(raw) {
        const source = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
        const levels = source.logLevels && typeof source.logLevels === 'object' ? source.logLevels : {};
        return {
            theme: oneOf(source.theme, THEMES, DEFAULTS.theme),
            textSize: oneOf(source.textSize, Object.keys(TEXT_SCALES), DEFAULTS.textSize),
            timeFormat: oneOf(source.timeFormat, TIME_FORMATS, DEFAULTS.timeFormat),
            defaultView: oneOf(source.defaultView, VIEWS, DEFAULTS.defaultView),
            showAllSpans: source.showAllSpans === true,
            logLevels: Object.fromEntries(LOG_LEVELS.map(level => [
                level, typeof levels[level] === 'boolean' ? levels[level] : DEFAULTS.logLevels[level],
            ])),
            slowReplySeconds: slowReply(source.slowReplySeconds),
            inspectorWidth: inspectorWidth(source.inspectorWidth),
        };
    }

    // Storage can be missing or throw (private windows, blocked site data).
    function storage() {
        try {
            return global.localStorage || null;
        } catch {
            return null;
        }
    }

    function load() {
        try {
            const text = storage()?.getItem(STORAGE_KEY);
            return sanitize(text ? JSON.parse(text) : {});
        } catch {
            return sanitize({});
        }
    }

    function apply(preferences) {
        const root = global.document?.documentElement;
        if (!root) return;
        root.dataset.palette = preferences.theme;
        root.style.setProperty('--text-scale', String(TEXT_SCALES[preferences.textSize]));
    }

    function announce(preferences) {
        if (typeof global.dispatchEvent === 'function' && typeof global.CustomEvent === 'function') {
            global.dispatchEvent(new global.CustomEvent(CHANGE_EVENT, { detail: preferences }));
        }
    }

    function save(changes) {
        const next = sanitize({ ...load(), ...changes });
        try {
            storage()?.setItem(STORAGE_KEY, JSON.stringify(next));
        } catch {
            // Not stored, but still applied to this page.
        }
        apply(next);
        announce(next);
        return next;
    }

    function reset() {
        try {
            storage()?.removeItem(STORAGE_KEY);
        } catch {
            // Nothing stored to remove.
        }
        const defaults = sanitize({});
        apply(defaults);
        announce(defaults);
        return defaults;
    }

    // A theme value from the CSS variables in app.css, e.g. cssToken('--chart-llm').
    function cssToken(name, fallback = '') {
        const root = global.document?.documentElement;
        if (!root || typeof global.getComputedStyle !== 'function') return fallback;
        return global.getComputedStyle(root).getPropertyValue(name).trim() || fallback;
    }

    function textScale() {
        return TEXT_SCALES[load().textSize];
    }

    function hour12() {
        return load().timeFormat === '12h';
    }

    // Keep other open tabs in step when preferences change in one of them.
    if (typeof global.addEventListener === 'function') {
        global.addEventListener('storage', event => {
            if (event.key !== STORAGE_KEY && event.key !== null) return;
            const preferences = load();
            apply(preferences);
            announce(preferences);
        });
    }

    apply(load());

    global.FinchvoxPreferences = Object.freeze({
        STORAGE_KEY, CHANGE_EVENT, THEMES, TEXT_SCALES, TIME_FORMATS, VIEWS, LOG_LEVELS,
        SLOW_REPLY_RANGE, INSPECTOR_WIDTH_RANGE, DEFAULTS,
        sanitize, load, save, reset, cssToken, textScale, hour12,
    });
})(typeof window !== 'undefined' ? window : globalThis);
