function logsViewMixin() {
    const LOG_PANEL_WIDTH_STORAGE_KEY = 'finchvox.inspectLogPanel.width';
    const DEFAULT_LOG_PANEL_WIDTH_PX = 400;
    const MIN_LOG_PANEL_WIDTH_PX = 320;
    const MAX_LOG_PANEL_WIDTH_PX = 900;
    const VALID_HASH_VIEWS = ['trace', 'conversation', 'metrics'];

    return {
        logCopied: false,
        selectedView: 'logs',
        logs: [],
        selectedLog: null,
        highlightedLogIndex: -1,
        isLogPanelOpen: false,
        logPanelWidth: DEFAULT_LOG_PANEL_WIDTH_PX,
        logPanelIsResizing: false,
        _logPanelResizeCleanup: null,
        _logPanelPrevBodyStyle: null,
        _logPanelWindowResizeHandler: null,
        logsLoading: false,
        logsTotalCount: 0,
        logsLimit: 1000,
        traceStartTime: null,
        logSearchQuery: '',
        logLevelFilters: {
            DEBUG: true,
            INFO: true,
            WARN: true,
            ERROR: true
        },

        initLogsView() {
            const hash = window.location.hash.slice(1);
            if (VALID_HASH_VIEWS.includes(hash)) {
                this.selectedView = hash;
            }

            this.initLogPanelSizing();
        },

        initLogPanelSizing() {
            try {
                const storedWidth = Number(localStorage.getItem(LOG_PANEL_WIDTH_STORAGE_KEY));
                if (Number.isFinite(storedWidth) && storedWidth > 0) {
                    this.logPanelWidth = storedWidth;
                }
            } catch {
                // Ignore storage failures (e.g. privacy mode / blocked storage)
            }
            this.logPanelWidth = this.clampLogPanelWidth(this.logPanelWidth);

            if (!this._logPanelWindowResizeHandler) {
                this._logPanelWindowResizeHandler = () => {
                    this.logPanelWidth = this.clampLogPanelWidth(this.logPanelWidth);
                };
                window.addEventListener('resize', this._logPanelWindowResizeHandler);
            }
        },

        clampLogPanelWidth(widthPx) {
            const viewportWidth = document.documentElement?.clientWidth || window.innerWidth || 0;

            const minWidth = Math.min(
                MIN_LOG_PANEL_WIDTH_PX,
                Math.max(240, viewportWidth - 80),
                viewportWidth
            );
            const maxCap = Math.min(MAX_LOG_PANEL_WIDTH_PX, viewportWidth);
            const preferredMax = Math.max(minWidth, viewportWidth - 240);
            const maxWidth = Math.min(maxCap, preferredMax);
            const safeWidth = Number.isFinite(widthPx) ? widthPx : DEFAULT_LOG_PANEL_WIDTH_PX;

            return Math.min(maxWidth, Math.max(minWidth, safeWidth));
        },

        setLogPanelWidth(widthPx, { persist = true } = {}) {
            this.logPanelWidth = this.clampLogPanelWidth(widthPx);
            if (persist) {
                try {
                    localStorage.setItem(LOG_PANEL_WIDTH_STORAGE_KEY, String(Math.round(this.logPanelWidth)));
                } catch {
                }
            }
        },

        _saveBodyStyleForLogResize() {
            this._logPanelPrevBodyStyle = {
                userSelect: document.body.style.userSelect,
                cursor: document.body.style.cursor
            };
            document.body.style.userSelect = 'none';
            document.body.style.cursor = 'col-resize';
        },

        _restoreBodyStyleAfterLogResize() {
            if (this._logPanelPrevBodyStyle) {
                document.body.style.userSelect = this._logPanelPrevBodyStyle.userSelect ?? '';
                document.body.style.cursor = this._logPanelPrevBodyStyle.cursor ?? '';
            }
            this._logPanelPrevBodyStyle = null;
        },

        _finishLogPanelResize() {
            if (!this.logPanelIsResizing) return;
            this.logPanelIsResizing = false;
            this.setLogPanelWidth(this.logPanelWidth, { persist: true });
            this._restoreBodyStyleAfterLogResize();
            if (this._logPanelResizeCleanup) {
                this._logPanelResizeCleanup();
                this._logPanelResizeCleanup = null;
            }
        },

        _shouldIgnoreLogResizeEvent(event) {
            if (!event) return true;
            if (event.pointerType === 'mouse' && event.button !== 0) return true;
            if (this._logPanelResizeCleanup) return true;
            return false;
        },

        _getLogViewportWidth() {
            return document.documentElement?.clientWidth || window.innerWidth || 0;
        },

        _trySetLogPointerCapture(event) {
            try {
                event.target?.setPointerCapture?.(event.pointerId);
            } catch {
            }
        },

        startLogPanelResize(event) {
            if (this._shouldIgnoreLogResizeEvent(event)) return;

            this.logPanelIsResizing = true;
            this._saveBodyStyleForLogResize();

            const updateFromPointer = (clientX) => {
                const desiredWidth = this._getLogViewportWidth() - clientX;
                this.setLogPanelWidth(desiredWidth, { persist: false });
            };

            const onMove = (e) => updateFromPointer(e.clientX);
            const finish = () => this._finishLogPanelResize();

            document.addEventListener('pointermove', onMove);
            document.addEventListener('pointerup', finish, { once: true });
            document.addEventListener('pointercancel', finish, { once: true });

            this._logPanelResizeCleanup = () => {
                document.removeEventListener('pointermove', onMove);
            };

            this._trySetLogPointerCapture(event);
            updateFromPointer(event.clientX);
        },

        loadLogsIfNeeded() {
            if (this.selectedView === 'logs') {
                this.loadLogs();
            }
        },

        handleLogsKeydown(event) {
            const logsHandlers = {
                ' ': () => this.togglePlay(),
                'ArrowLeft': () => this.skipBackward(5),
                'ArrowRight': () => this.skipForward(5),
                'ArrowUp': () => this.navigateLog(-1),
                'ArrowDown': () => this.navigateLog(1),
                'Escape': () => this.isLogPanelOpen && this.closeLogPanel(),
                'Enter': () => {
                    if (this.highlightedLogIndex >= 0) {
                        this.selectLog(this.logs[this.highlightedLogIndex], this.highlightedLogIndex);
                    }
                }
            };

            const handler = logsHandlers[event.key];
            if (handler) {
                event.preventDefault();
                handler();
                return true;
            }
            return false;
        },

        switchView(view) {
            this.selectedView = view;
            history.pushState(null, '', `#${view}`);

            this.closePanel();
            this.closeLogPanel();

            if (view === 'logs' && this.logs.length === 0) {
                this.loadLogs();
            }

            if (view === 'conversation' && this.conversationMessages.length === 0) {
                this.fetchConversation();
            }

            if (view === 'metrics') {
                this.loadMetricsIfNeeded();
            }
        },

        async loadLogs() {
            this.logsLoading = true;

            try {
                const response = await fetch(`/api/sessions/${this.sessionId}/logs?limit=${this.logsLimit}`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);

                const data = await response.json();
                this.logs = data.logs;
                this.logsTotalCount = data.total_count;
                this.traceStartTime = data.trace_start_time;
            } catch (error) {
                console.error('Failed to load logs:', error);
            } finally {
                this.logsLoading = false;
            }
        },

        selectLog(log, index) {
            this.selectedLog = log;
            this.highlightedLogIndex = index;
            this.isLogPanelOpen = true;
            this.seekToLog(log);
        },

        seekToLog(log) {
            if (!log?.time_unix_nano || !this.traceStartTime) return;

            this.highlightLog(log);

            if (this.wavesurfer && this.duration) {
                const isPlaying = this.wavesurfer.isPlaying();
                if (!isPlaying) {
                    const relativeNanos = log.time_unix_nano - this.traceStartTime;
                    const audioTime = relativeNanos / 1_000_000_000;
                    const progress = audioTime / this.duration;
                    this.wavesurfer.seekTo(progress);
                    this.currentTime = audioTime;
                }
            }
        },

        closeLogPanel() {
            this.isLogPanelOpen = false;
            this.selectedLog = null;
        },

        getFilteredLogs() {
            return this.logs.filter(log => {
                const level = (log.severity_text || '').toUpperCase();
                const normalizedLevel = (level === 'WARNING') ? 'WARN' :
                                        (level === 'FATAL' || level === 'CRITICAL') ? 'ERROR' : level;
                if (!this.logLevelFilters[normalizedLevel]) {
                    return false;
                }

                if (this.logSearchQuery) {
                    const body = this.getLogBody(log).toLowerCase();
                    if (!body.includes(this.logSearchQuery.toLowerCase())) {
                        return false;
                    }
                }

                return true;
            });
        },

        toggleLogLevel(level) {
            this.logLevelFilters[level] = !this.logLevelFilters[level];
        },

        formatLogRelativeTime(timestamp) {
            if (!timestamp || !this.traceStartTime) return '';
            const relativeNanos = timestamp - this.traceStartTime;
            const relativeMs = relativeNanos / 1_000_000;
            return formatDuration(relativeMs);
        },

        formatLogTimestamp(timestamp) {
            if (!timestamp) return '';
            const date = new Date(Number(timestamp) / 1_000_000);
            const options = {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: true
            };
            const formatted = date.toLocaleString('en-US', options);
            const ms = date.getMilliseconds().toString().padStart(3, '0');
            return `${formatted}.${ms}`;
        },

        getLogLevelClass(level) {
            if (!level) return 'text-white/70';
            const levelColors = {
                'WARN': 'text-amber-400',
                'WARNING': 'text-amber-400',
                'ERROR': 'text-red-400',
                'FATAL': 'text-red-400',
                'CRITICAL': 'text-red-400'
            };
            return levelColors[level.toUpperCase()] || 'text-white/70';
        },

        getLogBody(log) {
            if (!log) return '';
            if (log.body?.string_value) {
                return log.body.string_value;
            }
            if (typeof log.body === 'string') {
                return log.body;
            }
            return JSON.stringify(log.body) || '';
        },

        getRawLogJSON(log) {
            if (!log) return '{}';
            return JSON.stringify(log, null, 2);
        },

        async copyLogToClipboard() {
            if (!this.selectedLog) return;

            try {
                const logJSON = this.getRawLogJSON(this.selectedLog);
                await navigator.clipboard.writeText(logJSON);

                this.logCopied = true;
                setTimeout(() => {
                    this.logCopied = false;
                }, 1500);
            } catch (err) {
                console.error('Failed to copy log:', err);
            }
        },

        navigateLog(direction) {
            if (this.logs.length === 0) return;

            const panelWasOpen = this.isLogPanelOpen;
            let targetIndex;

            if (this.highlightedLogIndex === -1) {
                targetIndex = direction === 1 ? 0 : this.logs.length - 1;
            } else {
                targetIndex = this.highlightedLogIndex + direction;
                if (targetIndex < 0 || targetIndex >= this.logs.length) return;
            }

            this.highlightedLogIndex = targetIndex;
            if (panelWasOpen) {
                this.selectedLog = this.logs[targetIndex];
            }

            this.scrollLogIntoView(targetIndex);
        },

        scrollLogIntoView(index) {
            const logElement = document.querySelector(`[data-log-index="${index}"]`);
            if (logElement) {
                logElement.scrollIntoView({
                    behavior: 'smooth',
                    block: 'nearest'
                });
            }
        },

        canHighlightLog(log) {
            return log?.time_unix_nano && this.traceStartTime && this.duration;
        },

        highlightLog(log) {
            if (!this.canHighlightLog(log)) return;

            const relativeNanos = log.time_unix_nano - this.traceStartTime;
            const relativeSeconds = relativeNanos / 1_000_000_000;

            this.hoverMarker.time = relativeSeconds;
            this.hoverMarker.source = 'logs';
            this.hoverMarker.visible = true;
        },

        unhighlightLog() {
            if (this.hoverMarker.source === 'logs') {
                this.hoverMarker.visible = false;
            }
        },

        logHasSpan() {
            return this.selectedLog?.span_id_hex && this.selectedLog.span_id_hex.length > 0;
        }
    };
}
