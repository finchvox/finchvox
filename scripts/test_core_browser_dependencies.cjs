const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const WaveSurfer = require('../ui/lib/wavesurfer.min.js');
const Chart = require('../ui/lib/chart.min.js');
const appSource = readFileSync(join(__dirname, '../ui/js/session_detail.js'), 'utf8');
const metricsSource = readFileSync(join(__dirname, '../ui/js/metrics_view.js'), 'utf8');
const conversationSource = readFileSync(join(__dirname, '../ui/js/conversation.js'), 'utf8');
const logsSource = readFileSync(join(__dirname, '../ui/js/logs_view.js'), 'utf8');
// Every page loads preferences.js first; the views read theme colours through it.
const preferencesSource = readFileSync(join(__dirname, '../ui/js/preferences.js'), 'utf8');
const logFormatterSource = readFileSync(join(__dirname, '../ui/js/log_message_formatter.js'), 'utf8');
const alpineSource = readFileSync(join(__dirname, '../ui/lib/alpine.min.js'), 'utf8');

function loadAlpineReactivity(context) {
    context.window ??= {};
    context.window.Element = class {};
    context.document.createElement = () => ({});
    context.MutationObserver = class {};
    // Load the actual released reactivity engine without starting DOM traversal.
    context.queueMicrotask = () => {};
    vm.runInNewContext(alpineSource, context);
    return context.window.Alpine;
}

// Model only the documented player API. Actual rendering/decoding is checked in
// the browser; v8 no longer has the private v7 fields the old test fabricated.
class PlayerStub {
    constructor() {
        this.listeners = new Map();
        this.currentTime = 0;
        this.paused = true;
        this.destroyCount = 0;
    }
    on(event, listener) {
        const listeners = this.listeners.get(event) || new Set();
        listeners.add(listener);
        this.listeners.set(event, listeners);
        return () => listeners.delete(listener);
    }
    emit(event, value) {
        this.listeners.get(event)?.forEach(listener => listener(value));
    }
    load() { return Promise.resolve(); }
    getDuration() { return 120; }
    getCurrentTime() { return this.currentTime; }
    isPlaying() { return !this.paused; }
    seekTo(progress) {
        this.currentTime = progress * this.getDuration();
        this.emit('timeupdate', this.currentTime);
    }
    pause() { this.paused = true; this.emit('pause'); }
    playPause() {
        this.paused = !this.paused;
        this.emit(this.paused ? 'pause' : 'play');
        return Promise.resolve();
    }
    destroy() { this.destroyCount++; this.listeners.clear(); }
    setOptions(options) { this.lastOptions = options; this.setOptionsCount = (this.setOptionsCount || 0) + 1; }
}

function createAudioApp() {
    const players = [];
    const context = {
        WaveSurfer: { create: () => {
            const player = new PlayerStub();
            players.push(player);
            return player;
        } },
        document: Object.assign(new EventTarget(), {
            documentElement: {},
            getElementById: () => null,
        }),
        window: Object.assign(new EventTarget(), { CustomEvent }),
        getComputedStyle: () => ({ getPropertyValue: () => '#ffffff' }),
        metricsViewMixin: () => ({ destroyMetricsCharts() {} }),
        environmentViewMixin: () => ({}),
    };
    const alpine = loadAlpineReactivity(context);
    const app = alpine.reactive(vm.runInNewContext(
        `${preferencesSource}\n${logFormatterSource}\n${logsSource}\n${conversationSource}\n${appSource}\nsessionDetailApp();`, context));
    app.sessionId = 'test-session';
    app.initAudioPlayer();
    app.duration = players[0].getDuration();
    return { app, player: players[0], players, context, alpine };
}

test('the real Alpine reactivity engine does not proxy the native player', () => {
    const { app, player, alpine } = createAudioApp();
    assert.notEqual(app, alpine.raw(app));
    assert.equal(app.getAudioPlayer(), player);
    assert.equal(alpine.raw(app.getAudioPlayer()), app.getAudioPlayer());
});

test('paused WaveSurfer seeks update the replay position in seconds', () => {
    const { app, player } = createAudioApp();

    player.seekTo(0.25);

    assert.equal(player.paused, true);
    assert.equal(player.getCurrentTime(), 30);
    assert.equal(app.currentTime, 30);
});

test('destroy and reinitialize create a new v8 player instead of reusing a destroyed one', () => {
    const { app, player, players } = createAudioApp();
    app.initAudioPlayer();
    assert.equal(players.length, 1);
    assert.ok(Object.isFrozen(app.audioPlayer));

    app.destroy();
    app.destroy();
    assert.equal(player.destroyCount, 1);
    assert.equal(app.getAudioPlayer(), null);
    assert.equal(app.duration, 0);

    app.initAudioPlayer();
    assert.equal(players.length, 2);
    assert.notEqual(app.getAudioPlayer(), player);
});

test('cancelled loads do not set an audio error, but real failures do', async () => {
    const { app, player } = createAudioApp();
    player.load = () => Promise.reject(Object.assign(new Error('superseded'), { name: 'AbortError' }));
    await app.loadAudio('/cancelled.wav');
    assert.equal(app.audioError, false);

    player.load = () => Promise.reject(new Error('decode failed'));
    await app.loadAudio('/invalid.wav');
    assert.equal(app.audioError, true);
});

test('a late load failure cannot modify a destroyed component', async () => {
    const { app, player } = createAudioApp();
    let rejectLoad;
    player.load = () => new Promise((resolve, reject) => { rejectLoad = reject; });
    const loading = app.loadAudio('/pending.wav');
    app.destroy();
    rejectLoad(new Error('component closed'));
    await loading;
    assert.equal(app.audioError, false);
});

test('playback rejections are handled without changing a replacement player', async () => {
    const { app, player } = createAudioApp();
    let rejectPlayback;
    player.playPause = () => new Promise((resolve, reject) => { rejectPlayback = reject; });
    app.togglePlay();
    app.destroy();
    app.initAudioPlayer();
    app.togglePlay();
    rejectPlayback(new Error('old playback cancelled'));
    await Promise.resolve();
    assert.equal(app.playing, true);

    app.getAudioPlayer().playPause = () => Promise.reject(new Error('autoplay denied'));
    app.togglePlay();
    await Promise.resolve();
    assert.equal(app.playing, false);
});

test('transcript and log seeks use the native player and shared session clock', () => {
    const { app, player } = createAudioApp();
    app.minTime = 1_000;
    app.traceStartTime = 1_000_000_000;
    app.seekToMessage({ timestamp: 6_000_000_000 });
    assert.equal(player.getCurrentTime(), 5);
    assert.equal(app.currentTime, 5);
    app.seekToLog({ time_unix_nano: 3_000_000_000 });
    assert.equal(player.getCurrentTime(), 2);
    assert.equal(app.currentTime, 2);
});

test('BFCache pagehide pauses, while final pagehide destroys and removes shortcuts', () => {
    const { app, player, context } = createAudioApp();
    app.initKeyboardShortcuts();
    app.initCleanup();
    app.initCleanup();
    player.playPause();
    context.window.dispatchEvent(Object.assign(new Event('pagehide'), { persisted: true }));
    assert.equal(player.paused, true);
    assert.equal(player.destroyCount, 0);
    context.window.dispatchEvent(Object.assign(new Event('pagehide'), { persisted: false }));
    assert.equal(player.destroyCount, 1);
    let shortcuts = 0;
    app.handleKeydown = () => { shortcuts++; };
    context.document.dispatchEvent(new Event('keydown'));
    assert.equal(shortcuts, 0);
});

test('chart teardown releases instances and does not accumulate hover listeners', () => {
    const canvas = new EventTarget();
    canvas.getContext = () => ({});
    const charts = [];
    class ChartStub {
        constructor() { this.destroyCount = 0; charts.push(this); }
        destroy() { this.destroyCount++; }
    }
    const context = {
        Chart: ChartStub, AbortController,
        document: { getElementById: () => canvas },
        window: new EventTarget(),
    };
    const alpine = loadAlpineReactivity(context);
    const app = alpine.reactive(vm.runInNewContext(
        `${preferencesSource}\n${metricsSource}\nmetricsViewMixin();`, context));
    app.metricsData = { services: ['llm'], series: { llm: { data_points: [{
        relative_time_ms: 10, ttfb_ms: 100, span_id: 'span-1',
    }] } } };
    let leaves = 0;
    app.hideMarkerFromMetrics = () => { leaves++; };
    app.initMetricsCharts();
    app.initMetricsCharts();

    assert.equal(charts[0].destroyCount, 1);
    assert.ok(Object.isFrozen(app.metricsCharts));
    assert.equal(app.metricsCharts.llm, charts[1]);
    assert.equal(alpine.raw(app.metricsCharts.llm), app.metricsCharts.llm);
    canvas.dispatchEvent(new Event('mouseleave'));
    assert.equal(leaves, 1);
    app.destroyMetricsCharts();
    assert.equal(charts[1].destroyCount, 1);
    canvas.dispatchEvent(new Event('mouseleave'));
    assert.equal(leaves, 1);
});

test('vendored assets match pinned upstream payloads byte-for-byte after their banner', () => {
    const manifest = JSON.parse(readFileSync(join(__dirname, '../ui/lib/vendor-manifest.json')));
    for (const pkg of manifest.packages) {
        const asset = readFileSync(join(__dirname, '../ui/lib', pkg.file));
        const headerEnd = asset.indexOf(Buffer.from(' */\n')) + 4;
        assert.ok(headerEnd > 4);
        assert.equal(createHash('sha256').update(asset.subarray(headerEnd)).digest('hex'),
            pkg.payload_sha256, pkg.name);
    }
    assert.equal(Chart.version, '4.6.1');
    assert.equal(typeof WaveSurfer.prototype.getState, 'function');
    assert.equal(typeof WaveSurfer.definePlugin, 'function');
});

test('Alpine pages rely on automatic init exactly once', () => {
    for (const page of ['sessions_list.html', 'session_detail.html']) {
        const html = readFileSync(join(__dirname, '../ui', page), 'utf8');
        assert.match(html, /x-data="\w+App\(\)"/);
        assert.doesNotMatch(html, /x-init="init\(\)"/);
    }
});

test('a theme or text-size change redraws the waveform; other settings do not', () => {
    const { app, player } = createAudioApp();
    const base = app.preferences;

    app.applyPreferences({ ...base, slowReplySeconds: 3, timeFormat: '24h' });
    assert.equal(player.setOptionsCount, undefined);
    assert.equal(app.preferences.slowReplySeconds, 3);

    app.applyPreferences({ ...app.preferences, theme: 'classic' });
    assert.equal(player.setOptionsCount, 1);
    assert.equal(player.lastOptions.splitChannels.length, 2);

    app.applyPreferences({ ...app.preferences, textSize: 'large' });
    assert.equal(player.setOptionsCount, 2);
});

test('a preference change from Settings reaches the open session page', () => {
    const { app, context } = createAudioApp();
    app.initPreferenceUpdates();
    context.window.FinchvoxPreferences.save({ slowReplySeconds: 4.5 });
    assert.equal(app.preferences.slowReplySeconds, 4.5);

    app.destroy();
    context.window.FinchvoxPreferences.save({ slowReplySeconds: 6 });
    assert.equal(app.preferences.slowReplySeconds, 4.5);
});

test('dragging the inspector edge sets its width within limits and saves it once', () => {
    const { app, context } = createAudioApp();
    context.document.documentElement.clientWidth = 1600;
    const saved = [];
    context.window.addEventListener('finchvox:preferences', event => saved.push(event.detail.inspectorWidth));
    assert.equal(app.inspectorWidth, 460);

    app.startInspectorResize({ button: 0, clientX: 1140, pointerId: 1 });
    assert.equal(app.inspectorResizing, true);
    context.document.dispatchEvent(Object.assign(new Event('pointermove'), { clientX: 900 }));
    assert.equal(app.inspectorWidth, 700);
    context.document.dispatchEvent(Object.assign(new Event('pointermove'), { clientX: 1500 }));
    assert.equal(app.inspectorWidth, 320);
    assert.deepEqual(saved, []);

    context.document.dispatchEvent(new Event('pointerup'));
    assert.equal(app.inspectorResizing, false);
    assert.deepEqual(saved, [320]);

    // Released: further moves no longer resize.
    context.document.dispatchEvent(Object.assign(new Event('pointermove'), { clientX: 900 }));
    assert.equal(app.inspectorWidth, 320);
});

test('the inspector keeps at least 240 px of page beside it', () => {
    const { app, context } = createAudioApp();
    context.document.documentElement.clientWidth = 1000;
    assert.equal(app.clampInspectorWidth(950), 760);
    assert.equal(app.clampInspectorWidth(100), 320);
});

test('arrow keys on the inspector edge widen and narrow it', () => {
    const { app, context } = createAudioApp();
    context.document.documentElement.clientWidth = 1600;
    app.nudgeInspector(1);
    assert.equal(app.inspectorWidth, 480);
    app.nudgeInspector(-1);
    app.nudgeInspector(-1);
    assert.equal(app.inspectorWidth, 440);
});

test('the Logs tab shows a one-line preview, a formatted message, and searches the decoded text', () => {
    const { app } = createAudioApp();
    const dictLog = { time_unix_nano: '1', severity_text: 'INFO',
        body: { string_value: "Tool result: {'item': 'latte', 'ok': True}" } };
    const escapedLog = { time_unix_nano: '2', severity_text: 'INFO', body: { string_value: 'first\\nsecond' } };
    app.logs = [dictLog, escapedLog];

    assert.ok(!app.getLogPreview(dictLog).includes('\n'));
    assert.ok(app.getLogBody(dictLog).split('\n').length > 1);
    assert.equal(app.getLogBody(escapedLog), 'first\nsecond');

    app.logSearchQuery = 'first second';
    assert.equal(app.getFilteredLogs().length, 0);
    app.logSearchQuery = 'second';
    assert.deepEqual(app.getFilteredLogs().map(log => log.time_unix_nano), ['2']);
});

test('the slow-reply mark follows the threshold from Settings', () => {
    const { app } = createAudioApp();
    app.getUserBotLatency = () => 2.5;

    app.preferences = { ...app.preferences, slowReplySeconds: 2 };
    assert.equal(app.isSlowLatency({}), true);
    app.preferences = { ...app.preferences, slowReplySeconds: 3 };
    assert.equal(app.isSlowLatency({}), false);
});

test('WaveSurfer playback timeupdate events update the replay position', () => {
    const { app, player } = createAudioApp();

    player.emit('timeupdate', 42.5);

    assert.equal(app.currentTime, 42.5);
});

test('seeking back to the beginning clears the replay position', () => {
    const { app, player } = createAudioApp();
    player.seekTo(0.75);

    player.seekTo(0);

    assert.equal(app.currentTime, 0);
});
