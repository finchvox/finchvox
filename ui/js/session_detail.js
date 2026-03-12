function sessionDetailApp() {
    return {
        sessionId: null,
        serviceName: null,      // Service name from first span with resource.attributes
        spans: [],              // Original spans from API
        waterfallSpans: [],     // Flat array in display order for waterfall view
        expandedSpanIds: new Set(), // Set of span IDs that are expanded
        expansionInitialized: false, // Flag to ensure we only auto-expand on first load
        isWaterfallExpanded: false, // Global expand/collapse state for the waterfall
        selectedSpan: null,      // Span shown in the details panel
        highlightedSpan: null,   // Span highlighted in the waterfall (for keyboard navigation)
        isPanelOpen: false,

        spanCopied: false,

        ...logsViewMixin(),
        ...conversationViewMixin(),
        ...metricsViewMixin(),
        ...environmentViewMixin(),
        ...tracePanelViewMixin(),
        ...audioPlayerMixin(),
        ...hoverMarkerMixin(),
        ...spanFormattingMixin(),

        minTime: 0,
        maxTime: 0,

        isPolling: false,
        pollInterval: null,
        lastSpanCount: 0,
        consecutiveErrors: 0,

        getActiveSidePanelWidth() {
            if (this.isLogPanelOpen) return this.logPanelWidth;
            if (this.isPanelOpen) return this.tracePanelWidth;
            return 0;
        },

        getMainContentStyle() {
            return `margin-right: ${this.getActiveSidePanelWidth()}px;`;
        },

        getHeaderInsetStyle() {
            return `right: ${this.getActiveSidePanelWidth()}px;`;
        },

        async init() {
            const pathParts = window.location.pathname.split('/');
            this.sessionId = pathParts[pathParts.length - 1];

            if (!this.sessionId) {
                console.error('No session ID in URL');
                return;
            }

            this.initLogsView();
            this.initTracePanelSizing();
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
            this.initCleanup();

            const hashParams = new URLSearchParams(window.location.hash.split('?')[1] || '');
            const spanId = hashParams.get('span');
            if (spanId && this.selectedView === 'trace') {
                this.selectSpanById(spanId);
            }
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
                this.extractServiceName();
                this.updateTimelineBounds();
                this.buildWaterfallTree();
            } catch (error) {
                console.error('Failed to load trace:', error);
            }
        },

        buildSpanHierarchy() {
            const childrenMap = {};
            const rootSpans = [];
            const spanIds = new Set(this.spans.map(s => s.span_id_hex));

            this.spans.forEach(span => {
                const parentId = span.parent_span_id_hex;
                const isRootOrOrphan = !parentId || !spanIds.has(parentId);

                if (isRootOrOrphan) {
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
                .filter(span => span.name === 'conversation')
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
            this.waterfallSpans = [...this.spans].sort((a, b) => a.startMs - b.startMs);
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
            // Expand all spans with children
            this.spans.forEach(span => {
                // Find children for this span
                const children = this.spans.filter(s => s.parent_span_id_hex === span.span_id_hex);
                if (children.length > 0) {
                    this.expandedSpanIds.add(span.span_id_hex);
                }
            });

            this.isWaterfallExpanded = true;
            this.buildWaterfallTree();
        },

        collapseAll() {
            // Collapse everything below turns (depth 2+)
            // Only expand conversation to show turns, but don't expand turns
            this.expandedSpanIds.clear();

            // Find all conversation spans and expand them (this shows turns but not their children)
            this.spans.forEach(span => {
                if (span.name === 'conversation') {
                    const children = this.spans.filter(s => s.parent_span_id_hex === span.span_id_hex);
                    if (children.length > 0) {
                        this.expandedSpanIds.add(span.span_id_hex);
                    }
                }
            });

            this.isWaterfallExpanded = false;
            this.buildWaterfallTree();
        },


        getSpanTypes() {
            const typeOrder = ['conversation', 'turn', 'stt', 'llm', 'tts'];
            const presentTypes = new Set(this.spans.map(s => s.name));

            const orderedTypes = typeOrder.filter(type => presentTypes.has(type));

            const otherTypes = [...presentTypes]
                .filter(type => !typeOrder.includes(type))
                .sort();

            return [...orderedTypes, ...otherTypes];
        },

        getSpansByType(type) {
            return this.spans
                .filter(s => s.name === type)
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
            return {
                [`bar-${span.name}`]: true,
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

        initCleanup() {
            // Stop polling when user navigates away
            window.addEventListener('beforeunload', () => {
                if (this.isPolling) {
                    this.stopPolling();
                }
            });
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
            if (this.wavesurfer && this.duration) {
                const isPlaying = this.wavesurfer.isPlaying();
                if (!isPlaying) {
                    const audioTime = (span.startMs - this.minTime) / 1000;
                    const progress = audioTime / this.duration;
                    this.wavesurfer.seekTo(progress);
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

        isDataReady() {
            return this.spans?.length > 0 && this.duration;
        },

        getChildSpansByName(parentSpan, name) {
            return this.spans.filter(s => s.parent_span_id_hex === parentSpan.span_id_hex && s.name === name);
        },

        collectTextFromSpans(spans, textGetter) {
            return spans.map(s => textGetter(s)).filter(Boolean).join(' ');
        },

        buildTurnChunk(turn) {
            const sttChildren = this.getChildSpansByName(turn, 'stt');
            const llmChildren = this.getChildSpansByName(turn, 'llm');

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
            return this.spans.filter(s => s.name === 'turn').map(turn => this.buildTurnChunk(turn));
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

        isConversationComplete(data) {
            const conversationSpan = data.spans.find(s => s.name === 'conversation');
            return conversationSpan && conversationSpan.end_time_unix_nano;
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
