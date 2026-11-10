function sessionDetailApp() {
    return {
        sessionId: null,
        serviceName: null,      // Service name from first span with resource.attributes
        platform: null,         // Platform type: 'pipecat' or 'livekit'
        spans: [],              // Original spans from API
        waterfallSpans: [],     // Flat array in display order for waterfall view
        expandedSpanIds: new Set(), // Set of span IDs that are expanded
        expansionInitialized: false, // Flag to ensure we only auto-expand on first load
        isWaterfallExpanded: false, // Global expand/collapse state for the waterfall
        // Display preferences from Settings, kept current by applyPreferences().
        preferences: window.FinchvoxPreferences.load(),
        showAllSpans: window.FinchvoxPreferences.load().showAllSpans, // Also list spans the adapter marks hidden
        selectedSpan: null,      // Span shown in the details panel
        highlightedSpan: null,   // Span highlighted in the waterfall (for keyboard navigation)
        hoveredSpan: null,       // Span being hovered over (for chunk highlighting)
        chunkHoveredSpan: null,  // Span hovered from chunk (applies .selected to waterfall)
        isPanelOpen: false,      // Controls panel visibility and transitions
        inspectorWidth: window.FinchvoxPreferences.load().inspectorWidth, // px, both inspectors
        inspectorResizing: false, // True while the inspector edge is being dragged

        // Audio state
        audioPlayer: null,
        // A getter's result is made reactive by Alpine, even with a frozen holder.
        getAudioPlayer() { return this.audioPlayer?.instance ?? null; },
        playing: false,
        currentTime: 0,
        duration: 0,
        audioError: false,

        // Copy state
        spanCopied: false,

        // Logs view mixin (state and methods from logs_view.js)
        ...logsViewMixin(),

        // Conversation view mixin (state and methods from conversation.js)
        ...conversationViewMixin(),

        // Metrics view mixin (state and methods from metrics_view.js)
        ...metricsViewMixin(),

        // Environment view mixin (state and methods from environment_view.js)
        ...environmentViewMixin(),

        // Timeline state
        minTime: 0,
        maxTime: 0,

        // Real-time polling state
        isPolling: false,
        pollInterval: null,
        lastSpanCount: 0,
        consecutiveErrors: 0,

        // Hover marker state
        hoverMarker: {
            visible: false,
            time: 0,
            source: null  // 'waveform' or 'waterfall'
        },

        async init() {
            const pathParts = window.location.pathname.split('/');
            this.sessionId = pathParts[pathParts.length - 1];

            if (!this.sessionId) {
                console.error('No session ID in URL');
                return;
            }

            this.initLogsView();
            await this.loadTraceData();
            this.loadLogsIfNeeded();
            this.loadConversationIfNeeded();
            this.loadMetricsIfNeeded();

            // Disabled: Real-time polling not currently supported for logs
            // const conversationSpan = this.spans.find(s => s.name === 'conversation');
            // const shouldPoll = !conversationSpan || // No conversation span yet - might be created later
            //                    (conversationSpan && !conversationSpan.end_time_unix_nano); // Conversation exists but not ended
            //
            // if (shouldPoll) {
            //     this.startPolling();
            // }

            this.initAudioPlayer();
            this.initKeyboardShortcuts();
            this.initTimelineResize();
            this.initPreferenceUpdates();
            this.initCleanup();

            const hashParams = new URLSearchParams(window.location.hash.split('?')[1] || '');
            const spanId = hashParams.get('span');
            if (spanId && this.selectedView === 'trace') {
                this.selectSpanById(spanId);
            }
        },

        isAgentInsightsView() {
            return ['conversation', 'trace', 'logs'].includes(this.selectedView);
        },

        enrichSpan(span) {
            return {
                ...span,
                startMs: Number(span.start_time_unix_nano) / 1_000_000,
                endMs: Number(span.end_time_unix_nano) / 1_000_000,
                durationMs: (Number(span.end_time_unix_nano) - Number(span.start_time_unix_nano)) / 1_000_000
            };
        },

        updateTimelineBounds() {
            if (this.spans.length === 0) return;
            this.minTime = Math.min(...this.spans.map(s => s.startMs));
            this.maxTime = Math.max(...this.spans.map(s => s.endMs));
        },

        extractServiceName() {
            for (const span of this.spans) {
                const attrs = span.resource?.attributes;
                if (!attrs) continue;
                const serviceAttr = attrs.find(attr => attr.key === 'service.name');
                if (serviceAttr?.value?.string_value) {
                    this.serviceName = serviceAttr.value.string_value;
                    return;
                }
            }
        },

        async loadTraceData() {
            try {
                const response = await fetch(`/api/sessions/${this.sessionId}/trace`);
                const data = await response.json();

                this.spans = data.spans.map(span => this.enrichSpan(span));
                this.platform = data.platform || 'pipecat';
                this.extractServiceName();
                this.updateTimelineBounds();
                this.buildWaterfallTree();
            } catch (error) {
                console.error('Failed to load trace:', error);
            }
        },

        isSpanShownInTree(span) {
            return this.showAllSpans || !span._normalized?.hidden;
        },

        // The nearest ancestor shown in the tree, so hiding a wrapper span
        // (LiveKit's job_entrypoint or llm_node) moves its children up a level.
        shownParentId(span, spansById) {
            const visited = new Set();
            let parent = spansById.get(span.parent_span_id_hex);
            while (parent && !this.isSpanShownInTree(parent) && !visited.has(parent.span_id_hex)) {
                visited.add(parent.span_id_hex);
                parent = spansById.get(parent.parent_span_id_hex);
            }
            return parent && this.isSpanShownInTree(parent) ? parent.span_id_hex : null;
        },

        buildSpanHierarchy() {
            const childrenMap = {};
            const rootSpans = [];
            const spansById = new Map(this.spans.map(s => [s.span_id_hex, s]));

            this.spans.filter(span => this.isSpanShownInTree(span)).forEach(span => {
                const parentId = this.shownParentId(span, spansById);

                if (!parentId) {
                    rootSpans.push(span);
                } else {
                    if (!childrenMap[parentId]) childrenMap[parentId] = [];
                    childrenMap[parentId].push(span);
                }
            });

            Object.values(childrenMap).forEach(children => {
                children.sort((a, b) => a.startMs - b.startMs);
            });
            rootSpans.sort((a, b) => a.startMs - b.startMs);

            return { childrenMap, rootSpans };
        },

        flattenSpanTree(rootSpans, childrenMap) {
            const result = [];

            const traverse = (span, depth) => {
                span.depth = depth;
                span.children = childrenMap[span.span_id_hex] || [];
                span.childCount = span.children.length;
                result.push(span);

                if (this.expandedSpanIds.has(span.span_id_hex)) {
                    span.children.forEach(child => traverse(child, depth + 1));
                }
            };

            rootSpans.forEach(span => traverse(span, 0));
            return result;
        },

        initializeDefaultExpansion(childrenMap) {
            if (this.expansionInitialized) return false;

            let addedExpansions = false;
            this.spans
                .filter(span => ['root', 'turn'].includes(span._normalized?.category))
                .forEach(span => {
                    const children = childrenMap[span.span_id_hex] || [];
                    if (children.length > 0 && !this.expandedSpanIds.has(span.span_id_hex)) {
                        this.expandedSpanIds.add(span.span_id_hex);
                        addedExpansions = true;
                    }
                });

            this.expansionInitialized = true;
            this.isWaterfallExpanded = false;
            return addedExpansions;
        },

        buildWaterfallTree() {
            const { childrenMap, rootSpans } = this.buildSpanHierarchy();
            this.initializeDefaultExpansion(childrenMap);
            this.waterfallSpans = this.flattenSpanTree(rootSpans, childrenMap);
        },

        toggleSpanExpansion(span) {
            if (span.childCount === 0) {
                // No children, just select the span
                this.selectSpan(span);
                return;
            }

            // Toggle expansion state
            if (this.expandedSpanIds.has(span.span_id_hex)) {
                this.expandedSpanIds.delete(span.span_id_hex);
            } else {
                this.expandedSpanIds.add(span.span_id_hex);
            }

            // Rebuild the waterfall tree
            this.buildWaterfallTree();
        },

        toggleWaterfallExpansion() {
            if (this.isWaterfallExpanded) {
                this.collapseAll();
            } else {
                this.expandAll();
            }
        },

        expandAll() {
            const { childrenMap } = this.buildSpanHierarchy();
            Object.keys(childrenMap).forEach(spanId => this.expandedSpanIds.add(spanId));

            this.isWaterfallExpanded = true;
            this.buildWaterfallTree();
        },

        collapseAll() {
            const { childrenMap } = this.buildSpanHierarchy();
            this.expandedSpanIds.clear();

            this.spans.forEach(span => {
                if (span._normalized?.category === 'root' && childrenMap[span.span_id_hex]) {
                    this.expandedSpanIds.add(span.span_id_hex);
                }
            });

            this.isWaterfallExpanded = false;
            this.buildWaterfallTree();
        },

        hasHiddenSpans() {
            return this.spans.some(span => span._normalized?.hidden);
        },

        toggleShowAllSpans() {
            this.showAllSpans = !this.showAllSpans;
            if (this.showAllSpans) {
                // Open the wrapper spans that appear, so the spans already
                // listed stay visible beneath them.
                const { childrenMap } = this.buildSpanHierarchy();
                this.spans
                    .filter(span => span._normalized?.hidden && childrenMap[span.span_id_hex])
                    .forEach(span => this.expandedSpanIds.add(span.span_id_hex));
            }
            this.buildWaterfallTree();
        },


        getSpanTypes() {
            const typeInfo = new Map();

            this.spans.forEach(span => {
                if (span._normalized?.hidden) return;

                const displayName = span._normalized?.display_name || span.name.toUpperCase();
                const sortOrder = span._normalized?.sort_order;
                const category = span._normalized?.category || 'other';

                if (!typeInfo.has(displayName)) {
                    typeInfo.set(displayName, { sortOrder, category });
                }
            });

            const categoryOrder = ['root', 'turn', 'stt', 'llm', 'tool', 'handoff', 'tts', 'transport', 'other'];

            return [...typeInfo.entries()]
                .sort((a, b) => {
                    const [nameA, infoA] = a;
                    const [nameB, infoB] = b;

                    if (infoA.sortOrder !== undefined && infoB.sortOrder !== undefined) {
                        return infoA.sortOrder - infoB.sortOrder;
                    }
                    if (infoA.sortOrder !== undefined) return -1;
                    if (infoB.sortOrder !== undefined) return 1;

                    const catIndexA = categoryOrder.indexOf(infoA.category);
                    const catIndexB = categoryOrder.indexOf(infoB.category);
                    if (catIndexA !== catIndexB) {
                        return catIndexA - catIndexB;
                    }
                    return nameA.localeCompare(nameB);
                })
                .map(([name]) => name);
        },

        getSpansByType(type) {
            return this.spans
                .filter(s => !s._normalized?.hidden && (s._normalized?.display_name || s.name.toUpperCase()) === type)
                .sort((a, b) => a.startMs - b.startMs);
        },

        shouldHideLabel(span) {
            const totalDuration = this.maxTime - this.minTime;
            if (totalDuration === 0) return false;

            const spans = this.getSpansByType(span.name);
            const spanIndex = spans.findIndex(s => s.span_id_hex === span.span_id_hex);
            if (spanIndex === -1) return false;

            const minWidthForInternalLabel = 4;
            const labelOverflowBuffer = 4;

            const widthPercent = (span.durationMs / totalDuration) * 100;
            const labelOverflows = widthPercent < minWidthForInternalLabel;

            if (!labelOverflows) return false;

            if (spanIndex < spans.length - 1) {
                const next = spans[spanIndex + 1];
                const endPercent = ((span.endMs - this.minTime) / totalDuration) * 100;
                const nextStartPercent = ((next.startMs - this.minTime) / totalDuration) * 100;
                const gap = nextStartPercent - endPercent;

                if (gap < labelOverflowBuffer) {
                    return true;
                }
            }

            return false;
        },

        getTimelineBarStyle(span) {
            const totalDuration = this.maxTime - this.minTime;
            if (!Number.isFinite(totalDuration) || totalDuration <= 0) {
                return { left: '0%', width: '0.15%', isShort: true };
            }
            const startPercent = ((span.startMs - this.minTime) / totalDuration) * 100;
            const durationPercent = (span.durationMs / totalDuration) * 100;
            let widthPercent = Math.max(durationPercent, 0.15);

            const spans = this.getSpansByType(span.name);
            const spanIndex = spans.findIndex(s => s.span_id_hex === span.span_id_hex);
            if (spanIndex !== -1 && spanIndex < spans.length - 1) {
                const nextSpan = spans[spanIndex + 1];
                const spanEndMs = span.startMs + span.durationMs;
                const gapMs = nextSpan.startMs - spanEndMs;
                const gapPercent = (gapMs / totalDuration) * 100;
                if (gapPercent < 0.3) {
                    widthPercent = Math.max(widthPercent - 0.3, 0.15);
                }
            }

            return {
                left: `${startPercent}%`,
                width: `${widthPercent}%`,
                isShort: durationPercent < 2
            };
        },

        getTimelineBarClasses(span) {
            const style = this.getTimelineBarStyle(span);
            const cssClass = span._normalized?.css_class || `bar-${span.name}`;
            return {
                [cssClass]: true,
                'short-bar': style.isShort
            };
        },

        getExpandButtonStyle(span) {
            const barStyle = this.getTimelineBarStyle(span);
            const startPercent = parseFloat(barStyle.left);

            // Position button 26px to the left of the bar (16px button + 10px gap)
            // But ensure it doesn't go below 2px from the left edge
            if (startPercent < 3) {
                // For spans starting near 0%, position button at the start of the timeline (2px)
                return {
                    left: '2px'
                };
            }

            return {
                left: `calc(${startPercent}% - 26px)`
            };
        },

        handleRowClick(span) {
            this.selectSpan(span, true);
        },

        // Waveform colours from the current theme (CSS variables in app.css).
        getWaveColors() {
            const token = window.FinchvoxPreferences.cssToken;
            return {
                user: {
                    waveColor: token('--span-stt', '#c8d0eb'),
                    progressColor: token('--span-stt-progress', '#8e9ac8'),
                },
                agent: {
                    waveColor: token('--wave-agent', '#a855f7'),
                    progressColor: token('--wave-agent-progress', '#7c3aed'),
                },
            };
        },

        initAudioPlayer() {
            // Only initialize if not already created
            if (this.getAudioPlayer()) {
                return;
            }

            const colors = this.getWaveColors();
            const player = WaveSurfer.create({
                container: '#waveform',
                waveColor: colors.agent.waveColor,
                progressColor: colors.agent.progressColor,
                cursorColor: '#ffffff',
                height: 40,
                barWidth: 2,
                barGap: 1,
                barRadius: 2,
                normalize: true,
                backend: 'WebAudio',
                // Channel 0 is the user, channel 1 the agent.
                splitChannels: [colors.user, colors.agent]
            });
            // Native player state/signals must not be wrapped in Alpine's proxies.
            this.audioPlayer = Object.freeze({ instance: player });

            // Event listeners
            player.on('play', () => { this.playing = true; });
            player.on('pause', () => { this.playing = false; });
            player.on('timeupdate', (time) => { this.currentTime = time; });
            player.on('ready', () => {
                this.duration = player.getDuration();
                console.log('Audio ready, duration:', this.duration);

                // Clear error state when audio loads successfully
                if (this.audioError) {
                    console.log('Audio loaded successfully, clearing error state');
                    this.audioError = false;
                }

                // Generate timeline markers
                this.generateTimeline();

                // Setup hover marker listeners
                this.initWaveformHover();
            });
            player.on('error', (error) => {
                console.error('Audio loading error:', error);
                this.audioError = true;
            });
            this.loadAudio(`/api/sessions/${this.sessionId}/audio`);
        },

        async loadAudio(url) {
            const player = this.getAudioPlayer();
            if (!player) return;
            try {
                await player.load(url);
            } catch (error) {
                // V8 rejects superseded loads and loads aborted during teardown.
                if (error.name !== 'AbortError' && this.getAudioPlayer() === player) {
                    this.audioError = true;
                }
            }
        },

        generateTimeline() {
            const timeline = document.getElementById('timeline');
            if (!timeline || !this.duration) return;

            timeline.innerHTML = ''; // Clear existing

            // Up to 15 equally spaced markers, about one per 70 px so labels
            // never overlap on narrow screens.
            const markerCount = Math.max(2, Math.min(15, Math.floor(timeline.clientWidth / 70)));
            const interval = this.duration / markerCount;

            // Create timeline container with relative positioning
            timeline.style.display = 'block';
            timeline.style.position = 'relative';
            timeline.style.width = '100%';
            timeline.style.height = '20px';

            for (let i = 0; i <= markerCount; i++) {
                const time = i * interval;
                const percent = (time / this.duration) * 100;

                const marker = document.createElement('div');
                marker.className = 'timeline-marker';
                marker.style.position = 'absolute';
                marker.style.left = `${percent}%`;
                marker.style.height = '20px';

                // Create tick mark
                const tick = document.createElement('div');
                tick.style.position = 'absolute';
                tick.style.left = '0';
                tick.style.bottom = '0';
                tick.style.width = '1px';
                tick.style.height = '3px';
                tick.style.backgroundColor = '#6b7280';

                // Create label
                const label = document.createElement('span');
                label.style.position = 'absolute';
                label.style.left = '0';
                label.style.top = '0';

                // Align first label left, last label right, middle labels centered
                if (i === 0) {
                    label.style.transform = 'translateX(0)';
                } else if (i === markerCount) {
                    label.style.transform = 'translateX(-100%)';
                } else {
                    label.style.transform = 'translateX(-50%)';
                }

                label.style.fontSize = '12px';
                label.style.color = '#9ca3af';
                label.style.fontFamily = 'monospace';
                label.textContent = this.formatTimelineLabel(time);

                marker.appendChild(tick);
                marker.appendChild(label);
                timeline.appendChild(marker);
            }
        },

        formatTimelineLabel(seconds) {
            // Convert seconds to milliseconds and use unified formatter with 0 decimals
            return formatDuration(seconds * 1000, 0);
        },

        togglePlay() {
            const player = this.getAudioPlayer();
            if (player) {
                player.playPause().catch(error => {
                    console.error('Audio playback error:', error);
                    if (this.getAudioPlayer() === player) this.playing = false;
                });
            }
        },

        skipBackward(seconds) {
            const player = this.getAudioPlayer();
            if (!player || !this.duration) return;

            const currentTime = player.getCurrentTime();
            const newTime = Math.max(0, currentTime - seconds);
            const progress = newTime / this.duration;

            player.seekTo(progress);
        },

        skipForward(seconds) {
            const player = this.getAudioPlayer();
            if (!player || !this.duration) return;

            const currentTime = player.getCurrentTime();
            const newTime = Math.min(this.duration, currentTime + seconds);
            const progress = newTime / this.duration;

            player.seekTo(progress);
        },

        isUserTyping() {
            const activeElement = document.activeElement;
            return activeElement && (
                activeElement.tagName === 'INPUT' ||
                activeElement.tagName === 'TEXTAREA' ||
                activeElement.contentEditable === 'true'
            );
        },

        handleKeydown(event) {
            if (this.isUserTyping()) return;

            if (this.selectedView === 'logs') {
                if (this.handleLogsKeydown(event)) return;
            }

            const handlers = {
                ' ': () => this.togglePlay(),
                'ArrowLeft': () => this.skipBackward(5),
                'ArrowRight': () => this.skipForward(5),
                'ArrowUp': () => this.navigateToPreviousSpan(),
                'ArrowDown': () => this.navigateToNextSpan(),
                'Escape': () => this.selectedSpan && this.closePanel(),
                'Enter': () => this.highlightedSpan && this.selectSpan(this.highlightedSpan, true)
            };

            const handler = handlers[event.key];
            if (handler) {
                event.preventDefault();
                handler();
            }
        },

        initKeyboardShortcuts() {
            if (this.keyboardHandler) return;

            this.keyboardHandler = (event) => this.handleKeydown(event);
            document.addEventListener('keydown', this.keyboardHandler);
        },

        // Follow Settings changes made here or in another tab.
        initPreferenceUpdates() {
            if (this.preferencesHandler) return;
            this.preferencesHandler = (event) => this.applyPreferences(event.detail);
            window.addEventListener(window.FinchvoxPreferences.CHANGE_EVENT, this.preferencesHandler);
        },

        // CSS follows the theme and text size by itself; the waveform and charts
        // are drawn on canvases, so they are redrawn with the new colours.
        applyPreferences(next) {
            const previous = this.preferences;
            this.preferences = next;
            if (!this.inspectorResizing) this.inspectorWidth = next.inspectorWidth;
            if (previous.theme === next.theme && previous.textSize === next.textSize) return;

            const colors = this.getWaveColors();
            this.getAudioPlayer()?.setOptions({
                waveColor: colors.agent.waveColor,
                progressColor: colors.agent.progressColor,
                splitChannels: [colors.user, colors.agent],
            });
            if (Object.keys(this.metricsCharts || {}).length) this.initMetricsCharts();
        },

        // Inspector width: drag its left edge, or use the arrow keys on it. It is
        // kept between 320 and 900 px and leaves at least 240 px of the page,
        // and saved with the display preferences when the drag ends.
        clampInspectorWidth(width) {
            const range = window.FinchvoxPreferences.INSPECTOR_WIDTH_RANGE;
            const viewport = document.documentElement?.clientWidth || window.innerWidth || 0;
            const max = viewport ? Math.max(range.min, Math.min(range.max, viewport - 240)) : range.max;
            return Math.round(Math.min(max, Math.max(range.min, width)));
        },

        startInspectorResize(event) {
            if ((event.button !== undefined && event.button !== 0) || this.inspectorResizing) return;
            this.inspectorResizing = true;
            const viewport = () => document.documentElement?.clientWidth || window.innerWidth || 0;
            const onMove = (move) => {
                this.inspectorWidth = this.clampInspectorWidth(viewport() - move.clientX);
            };
            const finish = () => {
                document.removeEventListener('pointermove', onMove);
                document.removeEventListener('pointerup', finish);
                document.removeEventListener('pointercancel', finish);
                this.inspectorResizing = false;
                this.saveInspectorWidth();
            };
            document.addEventListener('pointermove', onMove);
            document.addEventListener('pointerup', finish);
            document.addEventListener('pointercancel', finish);
            // Keeps the drag ending cleanly when the button is released outside the window.
            try {
                event.target?.setPointerCapture?.(event.pointerId);
            } catch {
                // Pointer capture is optional.
            }
        },

        nudgeInspector(direction) {
            this.inspectorWidth = this.clampInspectorWidth(this.inspectorWidth + direction * 20);
            this.saveInspectorWidth();
        },

        saveInspectorWidth() {
            window.FinchvoxPreferences.save({ inspectorWidth: this.inspectorWidth });
        },

        // Redraw the time labels when the window width changes.
        initTimelineResize() {
            const timeline = document.getElementById('timeline');
            if (!timeline || this.timelineResizeObserver) return;
            let lastWidth = timeline.clientWidth;
            this.timelineResizeObserver = new ResizeObserver(() => {
                if (timeline.clientWidth === lastWidth) return;
                lastWidth = timeline.clientWidth;
                this.generateTimeline();
            });
            this.timelineResizeObserver.observe(timeline);
        },

        initCleanup() {
            if (this.pageHideHandler) return;
            this.pageHideHandler = (event) => {
                if (event.persisted) {
                    this.stopPolling();
                    this.getAudioPlayer()?.pause();
                } else {
                    this.destroy();
                }
            };
            window.addEventListener('pagehide', this.pageHideHandler);
        },

        destroy() {
            this.stopPolling();
            document.removeEventListener('keydown', this.keyboardHandler);
            window.removeEventListener('pagehide', this.pageHideHandler);
            this.keyboardHandler = null;
            this.pageHideHandler = null;
            this.waveformHoverEvents?.abort();
            this.waveformHoverEvents = null;
            this.timelineResizeObserver?.disconnect();
            this.timelineResizeObserver = null;
            if (this.preferencesHandler) {
                window.removeEventListener(window.FinchvoxPreferences.CHANGE_EVENT, this.preferencesHandler);
                this.preferencesHandler = null;
            }
            const player = this.getAudioPlayer();
            this.audioPlayer = null;
            player?.destroy();
            this.destroyMetricsCharts();
            this.playing = false;
            this.currentTime = 0;
            this.duration = 0;
        },

        navigateSpan(direction) {
            if (this.waterfallSpans.length === 0) return;

            const panelWasOpen = this.selectedSpan !== null;
            const currentSpan = this.highlightedSpan || this.selectedSpan;

            let targetSpan;
            if (!currentSpan) {
                targetSpan = direction === 1
                    ? this.waterfallSpans[0]
                    : this.waterfallSpans[this.waterfallSpans.length - 1];
            } else {
                const currentIndex = this.waterfallSpans.findIndex(
                    s => s.span_id_hex === currentSpan.span_id_hex
                );
                const targetIndex = currentIndex + direction;
                if (targetIndex < 0 || targetIndex >= this.waterfallSpans.length) return;
                targetSpan = this.waterfallSpans[targetIndex];
            }

            this.highlightedSpan = targetSpan;
            if (panelWasOpen) {
                this.selectedSpan = targetSpan;
            }
            this.navigateToSpan(targetSpan);
        },

        navigateToNextSpan() {
            this.navigateSpan(1);
        },

        navigateToPreviousSpan() {
            this.navigateSpan(-1);
        },

        navigateToSpan(span) {
            // Show hover marker at span position (visual feedback only)
            this.showMarkerAtSpan(span);

            // Scroll the span into view
            setTimeout(() => {
                this.scrollSpanIntoView(span);
            }, 0);
        },

        seekToSpan(span) {
            // Show hover marker at span position
            this.showMarkerAtSpan(span);

            // Seek audio to span start time if audio is not playing
            const player = this.getAudioPlayer();
            if (player && this.duration) {
                const isPlaying = player.isPlaying();
                if (!isPlaying) {
                    const audioTime = (span.startMs - this.minTime) / 1000;
                    const progress = audioTime / this.duration;
                    player.seekTo(progress);
                    // Update currentTime directly for immediate UI feedback
                    this.currentTime = audioTime;
                }
            }

            // Scroll the span into view
            setTimeout(() => {
                this.scrollSpanIntoView(span);
            }, 0);
        },

        selectSpan(span, shouldSeekAudio = false) {
            const panelWasOpen = this.isPanelOpen;

            // Update selected span content (doesn't trigger transition)
            this.selectedSpan = span;
            this.highlightedSpan = span;  // Keep highlight in sync when clicking

            // Open panel if not already open (triggers transition only when opening)
            if (!panelWasOpen && span) {
                this.isPanelOpen = true;
            }

            // Seek audio to span start time if requested
            if (shouldSeekAudio) {
                this.seekToSpan(span);
            }

            // If panel state changed (opened), refresh marker position after transition
            if (!panelWasOpen && span) {
                setTimeout(() => {
                    this.refreshMarkerPosition();
                }, 350); // Wait for CSS transition (0.3s) + small buffer
            }

            if (span && this.selectedView === 'trace') {
                this.updateUrlWithSpan(span);
            }
        },

        closePanel() {
            this.isPanelOpen = false;  // Triggers close transition
            this.selectedSpan = null;  // Clear panel content
            this.clearSpanFromUrl();
            // Refresh marker position after panel closes
            setTimeout(() => {
                this.refreshMarkerPosition();
            }, 350); // Wait for CSS transition (0.3s) + small buffer
        },

        scrollSpanIntoView(span) {
            // Find the DOM element for this span
            const spanElement = document.querySelector(`[data-span-id="${span.span_id_hex}"]`);
            if (spanElement) {
                // Use native scrollIntoView with center alignment
                // This automatically handles edge cases (top/bottom boundaries)
                spanElement.scrollIntoView({
                    behavior: 'smooth',
                    // block: 'center',
                    inline: 'nearest'
                });
            }
        },

        handleSpanClick(span, event) {
            this.selectSpan(span, true);
        },

        formatTime(seconds) {
            // Convert seconds to milliseconds and use unified formatter
            if (!seconds) return formatDuration(0);
            return formatDuration(seconds * 1000);
        },

        formatSpanDuration(span) {
            // Format span duration using unified formatter
            if (!span) return '';
            return formatDuration(span.durationMs);
        },

        formatRelativeStartTime(span) {
            // Format relative start time using unified formatter
            if (!span) return '';
            const relativeMs = span.startMs - this.minTime;
            return formatDuration(relativeMs);
        },

        formatTimestamp(nanos) {
            if (!nanos) return '';
            const date = new Date(Number(nanos) / 1_000_000);
            return date.toISOString().replace('T', ' ').substring(0, 23);
        },

        formatAttributesArray(attributes) {
            if (!attributes) return '{}';
            const attrs = {};
            attributes.forEach(attr => {
                if (!attr?.value) return;
                for (const valueKey of ['string_value', 'int_value', 'double_value', 'bool_value', 'bytes_value', 'array_value', 'kvlist_value']) {
                    if (Object.prototype.hasOwnProperty.call(attr.value, valueKey)) {
                        attrs[attr.key] = attr.value[valueKey];
                        break;
                    }
                }
            });
            return JSON.stringify(attrs, null, 2);
        },

        formatAttributes(span) {
            return this.formatAttributesArray(span?.attributes);
        },

        formatResourceAttributes(span) {
            return this.formatAttributesArray(span?.resource?.attributes);
        },

        getTranscriptText(span) {
            if (!span) return '';
            if (span._normalized?.transcript) {
                return span._normalized.transcript;
            }
            if (!span.attributes) return '';
            const transcriptAttr = span.attributes.find(attr => attr.key === 'transcript');
            if (!transcriptAttr) return '';
            return transcriptAttr.value.string_value || '';
        },

        getOutputText(span) {
            if (!span) return '';
            if (span._normalized?.output_text) {
                return span._normalized.output_text;
            }
            if (!span.attributes) return '';
            const outputAttr = span.attributes.find(attr => attr.key === 'output');
            if (!outputAttr) return '';
            return outputAttr.value.string_value || '';
        },

        getTurnUserTranscript(span) {
            if (!span || span.name !== 'turn') return '';
            const sttChildren = this.getChildSpansByName(span, 'stt');
            return this.collectTextFromSpans(sttChildren, s => this.getTranscriptText(s));
        },

        getTurnBotText(span) {
            if (!span || span.name !== 'turn') return '';
            const llmChildren = this.getChildSpansByName(span, 'llm');
            return this.collectTextFromSpans(llmChildren, s => this.getOutputText(s));
        },

        // Get a specific attribute value
        getAttribute(span, key) {
            if (!span || !span.attributes) return null;
            const attr = span.attributes.find(a => a.key === key);
            if (!attr || !attr.value) return null;
            for (const valueKey of ['string_value', 'int_value', 'double_value', 'bool_value', 'bytes_value']) {
                if (Object.prototype.hasOwnProperty.call(attr.value, valueKey)) {
                    return attr.value[valueKey];
                }
            }
            if (attr.value.array_value?.values) {
                return attr.value.array_value.values.map(v => {
                    for (const valueKey of ['string_value', 'int_value', 'double_value', 'bool_value']) {
                        if (Object.prototype.hasOwnProperty.call(v, valueKey)) return v[valueKey];
                    }
                    return null;
                });
            }
            return null;
        },

        // Check if a specific attribute exists
        hasAttribute(span, key) {
            return this.getAttribute(span, key) !== null;
        },

        // Format a single attribute value as JSON or plain text
        formatAttributeValue(span, key) {
            const value = this.getAttribute(span, key);
            if (value === null) return '';

            // Try to parse as JSON for pretty printing
            try {
                const parsed = JSON.parse(value);
                return JSON.stringify(parsed, null, 2);
            } catch (e) {
                // If not JSON, return as plain text
                return value;
            }
        },

        getTTFB(span) {
            if (!span) return null;
            if (span._normalized?.ttfb_seconds !== null && span._normalized?.ttfb_seconds !== undefined) {
                return span._normalized.ttfb_seconds;
            }
            if (!span.attributes) return null;
            const value = this.getAttribute(span, 'metrics.ttfb');
            return value === null ? null : Number(value);
        },

        // Format TTFB value for display
        formatTTFB(span) {
            const ttfbSeconds = this.getTTFB(span);
            if (ttfbSeconds === null) return '';

            // Convert seconds to milliseconds and format
            return formatDuration(ttfbSeconds * 1000);
        },

        // Get user-bot latency value from span attributes
        getUserBotLatency(span) {
            if (!span) return null;
            if (span._normalized?.e2e_latency_seconds !== null && span._normalized?.e2e_latency_seconds !== undefined) {
                return Number(span._normalized.e2e_latency_seconds);
            }
            const value = this.getAttribute(span, 'turn.user_bot_latency_seconds') ?? this.getAttribute(span, 'lk.e2e_latency');
            return value === null ? null : Number(value);
        },

        // Check if latency is >= 2 seconds (slow response)
        isSlowLatency(span) {
            const latencySeconds = this.getUserBotLatency(span);
            return latencySeconds !== null && latencySeconds >= this.preferences.slowReplySeconds;
        },

        // Plain text (shown with x-text), marking replies of 2 s or more as slow.
        formatUserBotLatency(span) {
            const latencySeconds = this.getUserBotLatency(span);
            if (latencySeconds === null) return '';

            const formattedTime = formatDuration(latencySeconds * 1000);
            return this.isSlowLatency(span) ? `${formattedTime} · slow` : formattedTime;
        },

        // Get interruption status from span attributes
        wasInterrupted(span) {
            if (!span) return null;
            if (span._normalized?.interrupted !== undefined && span._normalized?.interrupted !== null) {
                return Boolean(span._normalized.interrupted);
            }
            const value = this.getAttribute(span, 'turn.was_interrupted') ?? this.getAttribute(span, 'lk.interrupted');
            return value === null ? null : Boolean(value);
        },

        hasException(span) {
            if (!span) return false;
            if (span._normalized?.is_error) return true;
            const status = span.status?.code;
            if (status === 2 || status === 'STATUS_CODE_ERROR' || status === 'ERROR') return true;
            if (this.hasAttribute(span, 'error.type') || this.getAttribute(span, 'lk.function_tool.is_error') === true) return true;
            return Boolean(span.events?.some(e => e.name === 'exception'));
        },

        getLivekitLlmInputMessages(span) {
            if (!span || !span.events) return [];

            const messageEvents = ['gen_ai.system.message', 'gen_ai.user.message', 'gen_ai.assistant.message'];
            return span.events
                .filter(e => messageEvents.includes(e.name))
                .map(e => {
                    const role = e.name.replace('gen_ai.', '').replace('.message', '');
                    const contentAttr = e.attributes?.find(a => a.key === 'content');
                    const content = contentAttr?.value?.string_value || '';
                    return { role, content };
                });
        },

        hasLivekitLlmInput(span) {
            return this.getLivekitLlmInputMessages(span).length > 0;
        },

        formatLivekitLlmInput(span) {
            const messages = this.getLivekitLlmInputMessages(span);
            return JSON.stringify(messages, null, 2);
        },

        getLivekitLlmChoice(span) {
            if (!span || !span.events) return null;

            const choiceEvent = span.events.find(e => e.name === 'gen_ai.choice');
            if (!choiceEvent) return null;

            const roleAttr = choiceEvent.attributes?.find(a => a.key === 'role');
            const contentAttr = choiceEvent.attributes?.find(a => a.key === 'content');

            return {
                role: roleAttr?.value?.string_value || 'assistant',
                content: contentAttr?.value?.string_value || ''
            };
        },

        hasLivekitLlmOutput(span) {
            return this.getLivekitLlmChoice(span) !== null;
        },

        formatLivekitLlmOutput(span) {
            const choice = this.getLivekitLlmChoice(span);
            if (!choice) return '{}';
            return JSON.stringify(choice, null, 2);
        },

        // Get raw span JSON (excluding computed properties)
        getRawSpanJSON(span) {
            if (!span) return '{}';

            // Exclude computed properties added by the frontend
            const { startMs, endMs, durationMs, depth, children, childCount, ...rawSpan } = span;

            return JSON.stringify(rawSpan, null, 2);
        },

        // Copy span JSON to clipboard with visual feedback
        async copySpanToClipboard() {
            if (!this.selectedSpan) return;

            try {
                const spanJSON = this.getRawSpanJSON(this.selectedSpan);
                await navigator.clipboard.writeText(spanJSON);

                // Visual feedback: set copied state
                this.spanCopied = true;

                // Reset after 1.5 seconds
                setTimeout(() => {
                    this.spanCopied = false;
                }, 1500);
            } catch (err) {
                console.error('Failed to copy span:', err);
            }
        },

        // Initialize waveform hover listeners
        initWaveformHover() {
            const waveformContainer = document.getElementById('waveform');
            if (!waveformContainer) return;
            this.waveformHoverEvents?.abort();
            this.waveformHoverEvents = new AbortController();
            const options = { signal: this.waveformHoverEvents.signal };

            waveformContainer.addEventListener('mousemove', (e) => {
                const rect = waveformContainer.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const percent = x / rect.width;
                const time = percent * this.duration;

                this.hoverMarker.time = time;
                this.hoverMarker.source = 'waveform';
                this.hoverMarker.visible = true;
            }, options);

            waveformContainer.addEventListener('mouseleave', () => {
                if (this.hoverMarker.source === 'waveform') {
                    this.hoverMarker.visible = false;
                }
            }, options);
        },

        // Show hover marker at span start time (called from waterfall row hover)
        showMarkerAtSpan(span) {
            // Calculate relative time from trace start (minTime is already in ms)
            const relativeMs = span.startMs - this.minTime;
            this.hoverMarker.time = relativeMs / 1000; // Convert to seconds
            this.hoverMarker.source = 'waterfall';
            this.hoverMarker.visible = true;
        },

        // Hide hover marker (called from waterfall row leave)
        hideMarkerFromWaterfall() {
            if (this.hoverMarker.source === 'waterfall') {
                this.hoverMarker.visible = false;
            }
        },

        // Refresh hover marker position (called when waveform width changes, e.g., panel open/close)
        refreshMarkerPosition() {
            if (this.hoverMarker.visible && this.hoverMarker.source === 'waterfall') {
                // Force Alpine to recalculate by triggering a reactive update
                // We temporarily store the time value, toggle visibility, and restore
                const savedTime = this.hoverMarker.time;
                this.hoverMarker.visible = false;
                this.$nextTick(() => {
                    this.hoverMarker.time = savedTime;
                    this.hoverMarker.visible = true;
                });
            }
        },

        // Get hover marker position in pixels
        getMarkerPosition() {
            if (!this.duration || !this.hoverMarker.visible) return '32px';

            const waveform = document.getElementById('waveform');
            if (!waveform) return '32px';

            const waveformWidth = waveform.offsetWidth;
            const percent = this.hoverMarker.time / this.duration;
            const offsetInWaveform = percent * waveformWidth;
            const totalOffset = 32 + offsetInWaveform;

            return `${totalOffset}px`;
        },

        // Format hover marker time label
        getMarkerTimeLabel() {
            if (!this.hoverMarker.visible) return '';
            return this.formatTime(this.hoverMarker.time);
        },

        // Highlight span when hovering over chunk or waterfall row
        highlightSpan(span) {
            this.hoveredSpan = span;
            this.showMarkerAtSpan(span);
        },

        // Unhighlight span when leaving chunk or waterfall row
        unhighlightSpan() {
            this.hoveredSpan = null;
            this.hideMarkerFromWaterfall();
        },

        // Highlight span from chunk hover (also applies .selected to waterfall)
        highlightSpanFromChunk(span) {
            this.hoveredSpan = span;
            this.chunkHoveredSpan = span;
            this.showMarkerAtSpan(span);
        },

        // Unhighlight span when leaving chunk
        unhighlightSpanFromChunk() {
            this.hoveredSpan = null;
            this.chunkHoveredSpan = null;
            this.hideMarkerFromWaterfall();
        },

        handleChunkClick(span) {
            this.selectSpan(span, true);
        },

        isDataReady() {
            return this.spans?.length > 0 && this.duration;
        },

        getChildSpansByName(parentSpan, name) {
            return this.spans.filter(s => s.parent_span_id_hex === parentSpan.span_id_hex && s.name === name);
        },

        collectTextFromSpans(spans, textGetter) {
            return spans.map(s => textGetter(s)).filter(Boolean).join(' ');
        },

        getChildSpansByCategory(parentSpan, category) {
            return this.spans.filter(s =>
                s.parent_span_id_hex === parentSpan.span_id_hex &&
                s._normalized?.category === category
            );
        },

        buildTurnChunk(turn) {
            const sttChildren = this.getChildSpansByCategory(turn, 'stt');
            const llmChildren = this.getChildSpansByCategory(turn, 'llm');

            return {
                span_id_hex: turn.span_id_hex,
                span: turn,
                humanText: this.collectTextFromSpans(sttChildren, s => this.getTranscriptText(s)),
                botText: this.collectTextFromSpans(llmChildren, s => this.getOutputText(s)),
                style: this.getTimelineBarStyle(turn),
                wasInterrupted: this.wasInterrupted(turn)
            };
        },

        getTurnChunks() {
            if (!this.isDataReady()) return [];

            if (this.platform === 'livekit' && this.conversationMessages?.length) {
                return this.conversationMessages.map((message, index) => {
                    const span = this.getMessageSpan(message);
                    if (!span) return null;
                    return {
                        span_id_hex: `${span.span_id_hex}-${message.role}-${index}`,
                        span,
                        humanText: message.role === 'user' ? message.content : '',
                        botText: message.role === 'assistant' ? message.content : '',
                        style: this.getTimelineBarStyle(span),
                        wasInterrupted: Boolean(message.was_interrupted),
                    };
                }).filter(Boolean);
            }

            return this.spans
                .filter(s => s._normalized?.category === 'turn')
                .map(turn => this.buildTurnChunk(turn));
        },

        getSpanDisplayName(span) {
            if (!span) return '';
            if (span._normalized?.event_kind === 'tool') {
                return span._normalized?.tool_name || this.getAttribute(span, 'gen_ai.tool.name') || this.getAttribute(span, 'lk.function_tool.name') || 'Tool call';
            }
            if (span._normalized?.event_kind === 'handoff') return 'Agent handoff';
            return span._normalized?.display_name || (span.name || 'span').replaceAll('_', ' ');
        },

        getSpanSubtitle(span) {
            if (!span) return '';
            const category = span._normalized?.category;
            if (category === 'llm') {
                return this.getAttribute(span, 'gen_ai.response.model') || this.getAttribute(span, 'gen_ai.request.model') || this.getAttribute(span, 'gen_ai.provider.name') || '';
            }
            if (category === 'tool') {
                return span._normalized?.tool_call_id || this.getAttribute(span, 'gen_ai.tool.call.id') || '';
            }
            if (category === 'handoff') {
                const from = span._normalized?.previous_agent_label || this.getAttribute(span, 'lk.previous_agent_label');
                const to = span._normalized?.agent_label || this.getAttribute(span, 'lk.agent_label') || this.getAttribute(span, 'gen_ai.agent.name');
                return [from, to].filter(Boolean).join(' → ');
            }
            if (category === 'turn' && this.getUserBotLatency(span) !== null) {
                return `Response ${this.formatUserBotLatency(span)}`;
            }
            return '';
        },

        getTraceTicks(count = 7) {
            const totalMs = this.maxTime - this.minTime;
            if (!Number.isFinite(totalMs) || totalMs <= 0 || count < 2) return [];
            return Array.from({ length: count }, (_, index) => {
                const percent = (index / (count - 1)) * 100;
                const relativeMs = totalMs * (index / (count - 1));
                return { percent, label: formatDuration(relativeMs) };
            });
        },

        getTraceErrorCount() {
            return this.spans.filter(span => this.hasException(span)).length;
        },

        getTraceRowClass(span) {
            if (this.hasException(span)) return 'trace-row-error';
            if (span._normalized?.event_kind === 'tool') return 'trace-row-tool';
            if (span._normalized?.event_kind === 'handoff') return 'trace-row-handoff';
            return '';
        },

        getErrorRegions() {
            return this.spans.filter(span => this.hasException(span)).map(span => ({
                span,
                style: this.getTimelineBarStyle(span)
            }));
        },

        getPlayheadStyle() {
            if (!this.duration || !Number.isFinite(this.currentTime)) return 'left: 0%';
            const percent = Math.max(0, Math.min(100, (this.currentTime / this.duration) * 100));
            return `left: ${percent}%`;
        },

        getInsightEvents() {
            const traceEvents = this.spans
                .filter(span => ['tool', 'handoff'].includes(span._normalized?.event_kind) || this.hasException(span))
                .map(span => ({
                    span,
                    kind: this.hasException(span) ? 'error' : span._normalized?.event_kind,
                    timestamp: span.start_time_unix_nano,
                    title: this.hasException(span)
                        ? (span._normalized?.error_message || `${this.getSpanDisplayName(span)} error`)
                        : this.getSpanDisplayName(span),
                    subtitle: this.getSpanSubtitle(span),
                    source: 'opentelemetry',
                }));

            const reportEvents = (this.conversationEvents || []).map(event => ({
                ...event,
                source: event.source || 'livekit_session_report',
            }));

            // SessionReport is richer for tool/handoff rows; keep trace errors and
            // suppress obvious duplicate tool/handoff records when both streams exist.
            const reportKeys = new Set(reportEvents.map(event => this.getInsightEventKey(event)));
            const merged = [
                ...reportEvents,
                ...traceEvents.filter(event => event.kind === 'error' || !reportKeys.has(this.getInsightEventKey(event))),
            ];
            return merged.sort((a, b) => Number(a.timestamp) - Number(b.timestamp));
        },

        getInsightEventKey(event) {
            const span = event?.span;
            const callId = span?._normalized?.tool_call_id || this.getAttribute(span, 'gen_ai.tool.call.id');
            if (callId) return `tool:${callId}`;
            if (event?.kind === 'handoff') {
                return `handoff:${event.subtitle || ''}`;
            }
            return `${event?.kind || 'event'}:${event?.title || ''}`;
        },

        getTranscriptFeedItems() {
            const messages = (this.conversationMessages || []).map(message => ({
                type: 'message',
                timestamp: message.timestamp,
                message
            }));
            const events = this.getInsightEvents().map(event => ({
                type: 'event',
                timestamp: event.timestamp,
                event
            }));
            return [...messages, ...events].sort((a, b) => Number(a.timestamp || 0) - Number(b.timestamp || 0));
        },

        getMessageSpan(message) {
            if (!message?.span_ids?.length) return null;
            for (const id of message.span_ids) {
                const span = this.spans.find(s => s.span_id_hex === id);
                if (span) return span;
            }
            return null;
        },

        selectConversationMessage(message) {
            this.seekToMessage(message);
            const span = this.getMessageSpan(message);
            if (span) this.selectSpan(span, false);
        },

        selectInsightEvent(event) {
            if (!event?.span) return;
            this.selectSpan(event.span, true);
        },

        getMessageMetrics(message) {
            const metrics = message?.metrics || {};
            const definitions = [
                ['e2e_latency', 'E2E'],
                ['llm_node_ttft', 'LLM TTFT'],
                ['tts_node_ttfb', 'TTS TTFB'],
                ['transcription_delay', 'STT'],
                ['end_of_turn_delay', 'EOU'],
                ['playback_latency', 'Playback'],
            ];
            return definitions.flatMap(([key, label]) => {
                const raw = metrics[key];
                const seconds = Number(raw);
                if (raw === null || raw === undefined || !Number.isFinite(seconds)) return [];
                return [{ key, label, value: `${Math.round(seconds * 1000)} ms` }];
            });
        },

        formatTranscriptConfidence(message) {
            const raw = message?.transcript_confidence;
            const confidence = Number(raw);
            if (raw === null || raw === undefined || !Number.isFinite(confidence)) return '';
            return `${(confidence * 100).toFixed(confidence >= 0.995 ? 0 : 1)}%`;
        },

        getSessionAgentLabel() {
            for (const span of this.spans) {
                const value = span._normalized?.agent_label || this.getAttribute(span, 'lk.agent_label') || this.getAttribute(span, 'gen_ai.agent.name') || this.getAttribute(span, 'lk.agent_name');
                if (value) return value;
            }
            return this.serviceName || 'Agent';
        },

        getSessionRoomName() {
            for (const span of this.spans) {
                const value = this.getAttribute(span, 'lk.pii.room_name') || this.getAttribute(span, 'lk.room_name') || this.getAttribute(span, 'room_id') || this.getAttribute(span, 'lk.room_sid') || this.getAttribute(span, 'lk.room_id');
                if (value) return value;
            }
            return '';
        },

        getImportantAttributes(span) {
            if (!span) return [];
            const preferred = [
                'gen_ai.operation.name', 'gen_ai.provider.name', 'gen_ai.request.model', 'gen_ai.response.model',
                'gen_ai.usage.input_tokens', 'gen_ai.usage.output_tokens', 'gen_ai.response.time_to_first_chunk',
                'lk.response.ttft', 'lk.response.ttfb', 'lk.e2e_latency', 'lk.transcription_delay', 'lk.end_of_turn_delay',
                'lk.on_user_turn_completed_delay', 'lk.speech.queue_wait', 'lk.interrupted', 'lk.interruption.source', 'lk.playout.position',
                'lk.agent_label', 'lk.previous_agent_label', 'lk.agent_name', 'lk.generation_id', 'lk.parent_generation_id', 'lk.generation_count', 'lk.speech_id',
                'lk.transcript_confidence', 'lk.eou.probability', 'lk.eou.outcome', 'lk.eou.source', 'lk.eou.detection_delay',
                'lk.pii.room_name', 'room_id', 'job_id', 'lk.room_sid', 'lk.job_id', 'lk.participant_id', 'lk.pii.participant_identity',
                'lk.provider_request_ids', 'lk.retry_count', 'lk.fallback.label', 'lk.fallback.index', 'lk.fallback.recovery', 'lk.tts.label',
                'lk.eou.language', 'lk.eou.from_cache', 'lk.eou.wait_duration', 'lk.eou.rearm_count', 'lk.is_interruption', 'lk.interruption.probability',
                'lk.blocking.duration', 'lk.blocking.severity', 'lk.blocking.task', 'lk.blocking.gc_time', 'lk.blocking.cpu_time',
                'lk.job.dispatch_latency', 'lk.dispatch_id', 'lk.close_reason', 'lk.disconnect_reason', 'lk.amd.category', 'lk.amd.reason',
                'gen_ai.tool.name', 'gen_ai.tool.call.id', 'lk.function_tool.name', 'lk.function_tool.is_error',
                'error.type'
            ];
            const result = [];
            preferred.forEach(key => {
                const value = this.getAttribute(span, key);
                if (value !== null && value !== undefined && value !== '') result.push({ key, value });
            });
            return result;
        },

        formatInspectorValue(value) {
            if (typeof value === 'string') {
                try { return JSON.stringify(JSON.parse(value), null, 2); } catch (_) { return value; }
            }
            if (typeof value === 'object') return JSON.stringify(value, null, 2);
            return String(value);
        },

        getSpanErrors(span) {
            if (!span) return [];
            const errors = [];
            if (span._normalized?.error_message) errors.push(span._normalized.error_message);
            if (span.status?.message) errors.push(span.status.message);
            (span.events || []).filter(e => e.name === 'exception').forEach(event => {
                const attrs = event.attributes || [];
                const message = attrs.find(a => a.key === 'exception.message')?.value?.string_value;
                const type = attrs.find(a => a.key === 'exception.type')?.value?.string_value;
                errors.push(message || type || 'Exception');
            });
            return [...new Set(errors.filter(Boolean))];
        },

        getChildErrors(span) {
            if (!span?.span_id_hex) return [];
            const byParent = new Map();
            this.spans.forEach(candidate => {
                const parent = candidate.parent_span_id_hex || '';
                if (!byParent.has(parent)) byParent.set(parent, []);
                byParent.get(parent).push(candidate);
            });

            const result = [];
            const stack = [...(byParent.get(span.span_id_hex) || [])];
            while (stack.length) {
                const child = stack.shift();
                if (this.hasException(child)) {
                    const errors = this.getSpanErrors(child);
                    result.push({
                        span_id: child.span_id_hex,
                        name: this.getSpanDisplayName(child),
                        message: errors[0] || child._normalized?.error_message || 'Child span failed',
                    });
                }
                stack.push(...(byParent.get(child.span_id_hex) || []));
            }
            return result;
        },

        getSpanTimingMetrics(span) {
            if (!span) return [];
            const normalized = span._normalized || {};
            const entries = [
                ['e2e', 'E2E', normalized.e2e_latency_seconds ?? this.getAttribute(span, 'lk.e2e_latency')],
                ['transcription', 'STT', normalized.transcription_delay_seconds ?? this.getAttribute(span, 'lk.transcription_delay')],
                ['endpointing', 'EOU', normalized.end_of_turn_delay_seconds ?? this.getAttribute(span, 'lk.end_of_turn_delay')],
                ['turn_hook', 'Turn hook', normalized.on_user_turn_completed_delay_seconds ?? this.getAttribute(span, 'lk.on_user_turn_completed_delay')],
                ['queue', 'Queue', normalized.queue_wait_seconds ?? this.getAttribute(span, 'lk.speech.queue_wait')],
                ['llm_ttft', 'LLM TTFT', this.getAttribute(span, 'lk.response.ttft') ?? this.getAttribute(span, 'gen_ai.response.time_to_first_chunk')],
                ['tts_ttfb', 'TTS TTFB', this.getAttribute(span, 'lk.response.ttfb')],
                ['playback', 'Playback', this.getAttribute(span, 'lk.playback_latency')],
            ];
            return entries.flatMap(([key, label, raw]) => {
                if (raw === null || raw === undefined || raw === '') return [];
                const seconds = Number(raw);
                if (!Number.isFinite(seconds)) return [];
                return [{ key, label, value: `${Math.round(seconds * 1000)} ms` }];
            });
        },

        getPrimarySpanText(span) {
            if (!span) return '';
            return span._normalized?.transcript || span._normalized?.output_text || span._normalized?.tool_output || span._normalized?.tool_arguments || '';
        },

        // Real-time polling methods
        startPolling() {
            if (this.isPolling) return;

            this.isPolling = true;
            this.lastSpanCount = this.spans.length;
            console.log('Starting real-time polling for synchronized trace updates');

            // Poll for new spans every 1 second (audio reloads when spans update)
            this.pollInterval = setInterval(() => {
                this.pollForSpans();
            }, 1000);
        },

        stopPolling() {
            if (!this.isPolling) return;

            console.log('Stopping real-time polling');
            this.isPolling = false;
            if (this.pollInterval) clearInterval(this.pollInterval);
            this.pollInterval = null;
        },

        async reloadAudioIfNotPlaying() {
            const player = this.getAudioPlayer();
            if (player && !player.isPlaying()) {
                console.log('Reloading audio waveform (synchronized with spans)');
                const audioUrl = `/api/sessions/${this.sessionId}/audio?t=${Date.now()}`;
                await this.loadAudio(audioUrl);
            } else if (player) {
                console.log('Audio is playing, skipping reload');
            }
        },

        isConversationComplete(data) {
            const rootSpan = data.spans.find(s => s._normalized?.category === 'root');
            return rootSpan && rootSpan.end_time_unix_nano;
        },

        isTraceAbandoned(data) {
            if (!data.last_span_time) return false;
            const lastSpanMs = Number(data.last_span_time) / 1_000_000;
            const tenMinutesMs = 10 * 60 * 1000;
            return (Date.now() - lastSpanMs) > tenMinutesMs;
        },

        mergeNewSpans(data) {
            if (data.spans.length <= this.lastSpanCount) return false;

            const existingSpanIds = new Set(this.spans.map(s => s.span_id_hex));
            const newSpans = data.spans
                .filter(s => !existingSpanIds.has(s.span_id_hex))
                .map(s => this.enrichSpan(s));

            this.spans.push(...newSpans);
            this.updateTimelineBounds();
            this.lastSpanCount = this.spans.length;
            return newSpans.length > 0;
        },

        async pollForSpans() {
            try {
                const response = await fetch(`/api/sessions/${this.sessionId}/trace`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);

                const data = await response.json();
                this.consecutiveErrors = 0;

                if (this.isConversationComplete(data) || this.isTraceAbandoned(data)) {
                    this.stopPolling();
                    return;
                }

                if (this.mergeNewSpans(data)) {
                    this.buildWaterfallTree();
                    await this.reloadAudioIfNotPlaying();
                }
            } catch (error) {
                console.error('Error polling for spans:', error);
                this.consecutiveErrors++;
                if (this.consecutiveErrors >= 3) {
                    this.stopPolling();
                }
            }
        },

        expandToSpan(span) {
            if (!this.isSpanShownInTree(span)) this.showAllSpans = true;
            let currentSpanId = span.parent_span_id_hex;
            while (currentSpanId) {
                const parent = this.spans.find(s => s.span_id_hex === currentSpanId);
                if (!parent) break;
                this.expandedSpanIds.add(parent.span_id_hex);
                currentSpanId = parent.parent_span_id_hex;
            }
            this.buildWaterfallTree();
        },

        selectSpanById(spanId) {
            const span = this.spans.find(s => s.span_id_hex === spanId);
            if (!span) return;
            this.expandToSpan(span);
            this.selectSpan(span, true);
        },

        updateUrlWithSpan(span) {
            const baseHash = this.selectedView;
            const newHash = span ? `${baseHash}?span=${span.span_id_hex}` : baseHash;
            history.replaceState(null, '', `#${newHash}`);
        },

        clearSpanFromUrl() {
            history.replaceState(null, '', `#${this.selectedView}`);
        },

        jumpToSpanFromLog() {
            if (!this.selectedLog?.span_id_hex) return;

            const span = this.spans.find(s => s.span_id_hex === this.selectedLog.span_id_hex);
            if (!span) return;

            this.closeLogPanel();
            this.expandToSpan(span);
            this.selectedView = 'trace';
            this.selectSpan(span, true);
            this.updateUrlWithSpan(span);
        }
    };
}
