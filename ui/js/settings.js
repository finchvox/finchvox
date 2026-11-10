/* The settings page. Display preferences live in preferences.js; the server
   section is read-only information from /api/settings/server. */
function settingsApp() {
    const store = window.FinchvoxPreferences;
    const sampleTime = new Date(2026, 10, 7, 14, 19);
    const timeExample = hour12 => sampleTime.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12 });

    return {
        prefs: store.load(),
        server: null,
        serverError: null,
        justSaved: false,
        savedTimer: null,

        themes: [
            { value: 'insights', label: 'Insights', hint: 'Current look', swatch: ['#c8d0eb', '#8c7dff', '#715ce1', '#55d8d0'] },
            { value: 'classic', label: 'Classic', hint: 'Original Finchvox colours', swatch: ['#f97316', '#ec4899', '#a855f7', '#10b981'] },
        ],
        textSizes: [
            { value: 'small', label: 'Small' },
            { value: 'default', label: 'Default' },
            { value: 'large', label: 'Large' },
        ],
        timeFormats: [
            { value: '12h', label: `12-hour (${timeExample(true)})` },
            { value: '24h', label: `24-hour (${timeExample(false)})` },
        ],
        views: [
            { value: 'conversation', label: 'Transcript' },
            { value: 'trace', label: 'Trace' },
            { value: 'logs', label: 'Logs' },
            { value: 'metrics', label: 'Metrics' },
        ],
        logLevels: store.LOG_LEVELS,
        slowRange: store.SLOW_REPLY_RANGE,

        init() {
            // Changes made in another tab arrive through preferences.js.
            window.addEventListener(store.CHANGE_EVENT, event => { this.prefs = event.detail; });
            this.loadServer();
        },

        update(changes) {
            this.prefs = store.save(changes);
            this.flashSaved();
        },

        toggleLevel(level) {
            this.update({ logLevels: { ...this.prefs.logLevels, [level]: !this.prefs.logLevels[level] } });
        },

        // Out-of-range or empty input is corrected, and the field shows the stored value.
        setSlowReply(input) {
            this.update({ slowReplySeconds: input.value });
            input.value = this.prefs.slowReplySeconds;
        },

        resetAll() {
            this.prefs = store.reset();
            this.flashSaved();
        },

        flashSaved() {
            this.justSaved = true;
            clearTimeout(this.savedTimer);
            this.savedTimer = setTimeout(() => { this.justSaved = false; }, 1800);
        },

        async loadServer() {
            try {
                const response = await fetch('/api/settings/server');
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                this.server = await response.json();
            } catch {
                this.serverError = 'Could not load the server information.';
            }
        },

        display(value) {
            return value === null || value === undefined || value === '' ? 'Not reported' : String(value);
        },

        // In a container the server only knows its own ports; the browser
        // address shows the port this machine actually uses for the UI.
        httpPortText() {
            if (!this.server?.in_container) return this.display(this.server?.http_port);
            const browserPort = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
            return `${browserPort} (${this.display(this.server.http_port)} inside the container)`;
        },

        // 0.0.0.0 inside a container is normal; compose.yaml decides what this
        // machine exposes (127.0.0.1 only, by default).
        hostText() {
            const host = this.display(this.server?.host);
            return this.server?.in_container ? `${host} inside the container` : host;
        },

        grpcPortText() {
            const port = this.display(this.server?.grpc_port);
            return this.server?.in_container ? `${port} inside the container` : port;
        },
    };
}
