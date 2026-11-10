function logsViewMixin() {
    return {
        logCopied: false,
        selectedView: 'conversation',
        logs: [],
        selectedLog: null,
        highlightedLogIndex: -1,
        isLogPanelOpen: false,
        logsLoading: false,
        logsTotalCount: 0,
        logsLimit: 1000,
        traceStartTime: null,
        logSearchQuery: '',
        // Which levels show at first, from Settings.
        logLevelFilters: { ...window.FinchvoxPreferences.load().logLevels },

        initLogsView() {
            // "#trace?span=<id>" links to a span, so only the part before "?" names the tab.
            const view = window.location.hash.slice(1).split('?')[0];
            const views = ['trace', 'conversation', 'logs', 'metrics', 'environment'];
            // A link to a specific tab wins; otherwise open the tab chosen in Settings.
            this.selectedView = views.includes(view) ? view : window.FinchvoxPreferences.load().defaultView;
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

            if (view === 'environment') {
                this.loadEnvironmentIfNeeded();
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

            const player = this.getAudioPlayer();
            if (player && this.duration) {
                const isPlaying = player.isPlaying();
                if (!isPlaying) {
                    const relativeNanos = log.time_unix_nano - this.traceStartTime;
                    const audioTime = relativeNanos / 1_000_000_000;
                    const progress = audioTime / this.duration;
                    player.seekTo(progress);
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
                    const needle = this.logSearchQuery.toLowerCase();
                    const body = logMessageFormatter.getSearchText(log).toLowerCase();
                    const logger = this.getLogLogger(log).toLowerCase();
                    if (!body.includes(needle) && !logger.includes(needle)) {
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
                hour12: this.preferences.timeFormat === '12h'
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

        getLogLogger(log) {
            if (!log) return '';
            const loggerAttr = (log.attributes || []).find(attr => attr?.key === 'logger.name');
            const attrValue = loggerAttr?.value?.string_value;
            return attrValue || log.instrumentation_scope?.name || log.resource?.attributes?.find(attr => attr?.key === 'service.name')?.value?.string_value || '';
        },

        // The message laid out for reading (Python dicts indented, escaped
        // newlines decoded), shown in the log inspector.
        getLogBody(log) {
            if (!log) return '';
            return logMessageFormatter.formatLogBody(logMessageFormatter.getLogBodyValue(log));
        },

        // One line, cut at 220 characters, for the log table.
        getLogPreview(log) {
            return logMessageFormatter.getPreviewText(log);
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
