const TRACE_PANEL_WIDTH_STORAGE_KEY = 'finchvox.tracePanel.width';
const DEFAULT_TRACE_PANEL_WIDTH_PX = 400;
const MIN_TRACE_PANEL_WIDTH_PX = 320;
const MAX_TRACE_PANEL_WIDTH_PX = 900;

const ICONS = {
    error: {
        viewBox: "0 0 24 24",
        path: "M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12ZM12 8.25a.75.75 0 0 1 .75.75v3.75a.75.75 0 0 1-1.5 0V9a.75.75 0 0 1 .75-.75Zm0 8.25a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Z",
        fillRule: "evenodd"
    },
    turtle: {
        viewBox: '0 0 512 512',
        path: 'M511.325,275.018c-0.416-0.982-0.974-1.799-1.54-2.432c-1.117-1.241-2.199-1.891-3.157-2.382c-1.808-0.892-3.391-1.274-5.107-1.633c-2.982-0.592-6.348-0.916-10.13-1.183c-5.64-0.4-12.13-0.633-18.419-1.016c-3.166-0.192-6.29-0.433-9.18-0.734c0.3-1.449,0.474-2.932,0.467-4.432c0.008-3.732-0.975-7.447-2.725-10.896c-1.757-3.458-4.24-6.698-7.372-9.831c-2.991-2.982-6.69-7.489-10.847-12.979c-7.289-9.613-16.045-22.243-26.233-35.738c-15.311-20.252-33.847-42.503-56.24-59.93c-11.196-8.714-23.376-16.212-36.63-21.56c-13.246-5.339-27.574-8.505-42.853-8.505c-23.292-0.008-44.302,7.356-62.796,18.544c-13.896,8.398-26.45,18.935-37.813,30.307c-17.036,17.045-31.44,35.955-43.486,52.45c-6.023,8.239-11.454,15.878-16.27,22.326c-2.757,3.69-5.314,6.981-7.648,9.763c-0.783-0.741-1.549-1.475-2.283-2.208c-3.582-3.599-6.489-7.139-8.672-12.03c-2.174-4.89-3.699-11.33-3.706-20.876c-0.009-8.781,1.332-20.143,4.673-34.872c0.642-2.832,0.95-5.656,0.95-8.43c0-6.448-1.691-12.571-4.573-17.961c-4.323-8.114-11.205-14.653-19.318-19.235c-8.139-4.574-17.578-7.214-27.316-7.223c-9.863-0.008-20.077,2.79-29.032,9.146c-8.181,5.824-13.979,11.18-17.953,16.495c-1.974,2.658-3.491,5.315-4.531,8.023C0.542,148.685,0,151.442,0,154.141c-0.008,3.124,0.742,6.106,1.974,8.672c1.075,2.258,2.491,4.216,4.057,5.906c2.741,2.966,5.94,5.182,9.139,6.998c4.816,2.691,9.722,4.449,13.496,5.599c0.332,0.1,0.649,0.2,0.974,0.283c1.442,21.226,4.307,38.638,8.081,53.033c6.131,23.392,14.728,38.87,23.317,49.425c4.282,5.274,8.547,9.305,12.346,12.462c3.799,3.158,7.156,5.474,9.464,7.215c5.465,4.098,10.696,7.047,15.687,8.996c3.673,1.433,7.223,2.316,10.613,2.683v0.009c4.799,2.874,16.695,9.555,35.147,16.694c-0.183,0.666-0.5,1.491-0.925,2.4c-1.124,2.432-2.99,5.464-5.123,8.463c-3.232,4.541-7.089,9.08-10.113,12.437c-1.516,1.675-2.808,3.058-3.724,4.024c-0.467,0.484-0.816,0.85-1.075,1.084l-0.15,0.166c-0.016,0.017-0.091,0.1-0.2,0.208c-0.792,0.758-3.816,3.69-6.956,7.898c-1.766,2.4-3.599,5.198-5.074,8.389c-1.458,3.199-2.616,6.798-2.64,10.888c-0.017,2.899,0.666,6.056,2.274,8.93c0.883,1.608,2.007,2.933,3.224,4.041c2.124,1.958,4.54,3.357,7.09,4.482c3.857,1.699,8.097,2.824,12.546,3.582c4.448,0.758,9.056,1.124,13.504,1.124c5.298-0.016,10.313-0.5,14.778-1.675c2.233-0.616,4.332-1.39,6.365-2.607c1.016-0.608,2.008-1.342,2.949-2.308c0.925-0.933,1.808-2.133,2.441-3.599c0.366-0.883,1.1-2.466,2.049-4.44c3.316-6.94,9.297-18.802,14.404-28.857c2.566-5.04,4.907-9.63,6.606-12.954c0.85-1.674,1.55-3.024,2.033-3.965c0.475-0.924,0.733-1.442,0.733-1.442l0.016-0.033l0.042-0.042c0.033-0.067,0.075-0.142,0.092-0.217c23.226,4.758,50.517,8.048,81.565,8.048c1.641,0,3.266,0,4.907-0.025h0.025c23.184-0.274,43.978-2.416,62.23-5.606c2.25,4.39,7.597,14.812,12.804,25.15c2.657,5.256,5.274,10.497,7.414,14.87c1.092,2.174,2.05,4.148,2.824,5.79c0.774,1.624,1.383,2.956,1.716,3.723c0.624,1.466,1.491,2.666,2.432,3.599c1.666,1.666,3.433,2.699,5.256,3.507c2.75,1.2,5.69,1.9,8.84,2.383c3.157,0.475,6.514,0.7,9.98,0.7c6.814-0.016,13.937-0.833,20.318-2.64c3.174-0.917,6.181-2.083,8.93-3.691c1.383-0.808,2.691-1.732,3.907-2.857c1.199-1.108,2.324-2.433,3.215-4.041c1.625-2.874,2.283-6.031,2.266-8.93c0-4.09-1.158-7.689-2.616-10.888c-2.215-4.774-5.223-8.722-7.681-11.638c-2.099-2.457-3.799-4.132-4.374-4.648v-0.016c-0.016-0.026-0.033-0.042-0.05-0.059c-0.024-0.016-0.024-0.033-0.042-0.033c-0.033-0.042-0.05-0.058-0.091-0.1c-0.991-0.991-5.665-5.806-10.422-11.654c-2.641-3.232-5.274-6.772-7.306-10.039c-0.7-1.107-1.308-2.199-1.832-3.215c20.868-7.689,33.806-15.295,38.438-18.227c0.883-0.05,1.848-0.125,2.907-0.225c7.248-0.725,18.752-2.816,30.956-7.847c6.098-2.516,12.354-5.774,18.269-10.022c5.914-4.249,11.488-9.497,16.103-15.953l0.166-0.242l0.158-0.258c0.341-0.575,0.666-1.241,0.916-2.024c0.241-0.776,0.408-1.683,0.408-2.641C512,277.21,511.759,276.027,511.325,275.018z'
    },
    interrupted: {
        viewBox: '0 0 24 24',
        path: 'M10.5 1.875a1.125 1.125 0 0 1 2.25 0v8.219c.517.162 1.02.382 1.5.659V3.375a1.125 1.125 0 0 1 2.25 0v10.937a4.505 4.505 0 0 0-3.25 2.373 8.963 8.963 0 0 1 4-.935A.75.75 0 0 0 18 15v-2.266a3.368 3.368 0 0 1 .988-2.37 1.125 1.125 0 0 1 1.591 1.59 1.118 1.118 0 0 0-.329.79v3.006h-.005a6 6 0 0 1-1.752 4.007l-1.736 1.736a6 6 0 0 1-4.242 1.757H10.5a7.5 7.5 0 0 1-7.5-7.5V6.375a1.125 1.125 0 0 1 2.25 0v5.519c.46-.452.965-.832 1.5-1.141V3.375a1.125 1.125 0 0 1 2.25 0v6.526c.495-.1.997-.151 1.5-.151V1.875Z'
    },
    tool: {
        viewBox: '0 0 24 24',
        path: 'M12 6.75a5.25 5.25 0 0 1 6.775-5.025.75.75 0 0 1 .313 1.248l-3.32 3.319c.063.475.276.934.641 1.299.365.365.824.578 1.3.64l3.318-3.319a.75.75 0 0 1 1.248.313 5.25 5.25 0 0 1-5.472 6.756c-1.018-.086-1.87.1-2.309.634L7.344 21.3A3.298 3.298 0 1 1 2.7 16.657l8.684-7.151c.533-.44.72-1.291.634-2.309A5.342 5.342 0 0 1 12 6.75ZM4.117 19.125a.75.75 0 0 1 .75-.75h.008a.75.75 0 0 1 .75.75v.008a.75.75 0 0 1-.75.75h-.008a.75.75 0 0 1-.75-.75v-.008Z'
    },
    link: {
        viewBox: '0 0 24 24',
        path: 'M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25'
    }
};

const ICON_STYLES = {
    default: 'width: 16px; height: 16px; display: inline-block; vertical-align: middle; margin-left: 2px; fill: currentColor;',
    small: 'width: 14px; height: 14px; display: inline-block; vertical-align: middle; margin-left: 1.5px; fill: currentColor;'
};

function getIcon(name, style = ICON_STYLES.default) {
    const icon = ICONS[name];
    const fillRule = icon.fillRule ? ` fill-rule="${icon.fillRule}" clip-rule="${icon.fillRule}"` : '';
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${icon.viewBox}" style="${style}"><path${fillRule} d="${icon.path}"/></svg>`;
}

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
        hoveredSpan: null,       // Span being hovered over (for chunk highlighting)
        chunkHoveredSpan: null,  // Span hovered from chunk (applies .selected to waterfall)
        isPanelOpen: false,      // Controls panel visibility and transitions
        tracePanelWidth: 400,
        tracePanelIsResizing: false,
        _tracePanelResizeCleanup: null,
        _tracePanelPrevBodyStyle: null,
        _tracePanelWindowResizeHandler: null,

        // Audio state
        wavesurfer: null,
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

        initTracePanelSizing() {
            try {
                const storedWidth = Number(localStorage.getItem(TRACE_PANEL_WIDTH_STORAGE_KEY));
                if (Number.isFinite(storedWidth) && storedWidth > 0) {
                    this.tracePanelWidth = storedWidth;
                }
            } catch {
            }
            this.tracePanelWidth = this.clampTracePanelWidth(this.tracePanelWidth);

            if (!this._tracePanelWindowResizeHandler) {
                this._tracePanelWindowResizeHandler = () => {
                    this.tracePanelWidth = this.clampTracePanelWidth(this.tracePanelWidth);
                };
                window.addEventListener('resize', this._tracePanelWindowResizeHandler);
            }
        },

        clampTracePanelWidth(widthPx) {
            const viewportWidth = document.documentElement?.clientWidth || window.innerWidth || 0;

            const minWidth = Math.min(
                MIN_TRACE_PANEL_WIDTH_PX,
                Math.max(240, viewportWidth - 80),
                viewportWidth
            );
            const maxCap = Math.min(MAX_TRACE_PANEL_WIDTH_PX, viewportWidth);
            const preferredMax = Math.max(minWidth, viewportWidth - 240);
            const maxWidth = Math.min(maxCap, preferredMax);
            const safeWidth = Number.isFinite(widthPx) ? widthPx : DEFAULT_TRACE_PANEL_WIDTH_PX;

            return Math.min(maxWidth, Math.max(minWidth, safeWidth));
        },

        setTracePanelWidth(widthPx, { persist = true } = {}) {
            this.tracePanelWidth = this.clampTracePanelWidth(widthPx);
            if (persist) {
                try {
                    localStorage.setItem(TRACE_PANEL_WIDTH_STORAGE_KEY, String(Math.round(this.tracePanelWidth)));
                } catch {
                }
            }
        },

        startTracePanelResize(event) {
            if (!event) return;
            if (event.pointerType === 'mouse' && event.button !== 0) return;
            if (this._tracePanelResizeCleanup) return;

            this.tracePanelIsResizing = true;

            const prevUserSelect = document.body.style.userSelect;
            const prevCursor = document.body.style.cursor;
            this._tracePanelPrevBodyStyle = { userSelect: prevUserSelect, cursor: prevCursor };
            document.body.style.userSelect = 'none';
            document.body.style.cursor = 'col-resize';

            const updateFromPointer = (clientX) => {
                const viewportWidth = document.documentElement?.clientWidth || window.innerWidth || 0;
                const desiredWidth = viewportWidth - clientX;
                this.setTracePanelWidth(desiredWidth, { persist: false });
            };

            const onMove = (e) => updateFromPointer(e.clientX);
            const finish = () => {
                if (!this.tracePanelIsResizing) return;
                this.tracePanelIsResizing = false;
                this.setTracePanelWidth(this.tracePanelWidth, { persist: true });

                if (this._tracePanelPrevBodyStyle) {
                    document.body.style.userSelect = this._tracePanelPrevBodyStyle.userSelect ?? '';
                    document.body.style.cursor = this._tracePanelPrevBodyStyle.cursor ?? '';
                }
                this._tracePanelPrevBodyStyle = null;

                if (this._tracePanelResizeCleanup) {
                    this._tracePanelResizeCleanup();
                    this._tracePanelResizeCleanup = null;
                }
            };

            document.addEventListener('pointermove', onMove);
            document.addEventListener('pointerup', finish, { once: true });
            document.addEventListener('pointercancel', finish, { once: true });

            this._tracePanelResizeCleanup = () => {
                document.removeEventListener('pointermove', onMove);
            };

            try {
                event.target?.setPointerCapture?.(event.pointerId);
            } catch {
            }

            updateFromPointer(event.clientX);
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

        initAudioPlayer() {
            // Only initialize if not already created
            if (this.wavesurfer) {
                return;
            }

            this.wavesurfer = WaveSurfer.create({
                container: '#waveform',
                waveColor: '#a855f7',      // Purple (fallback)
                progressColor: '#7c3aed',  // Darker purple (fallback)
                cursorColor: '#ffffff',
                height: 40,
                barWidth: 2,
                barGap: 1,
                barRadius: 2,
                normalize: true,
                backend: 'WebAudio',
                splitChannels: [
                    {
                        waveColor: getComputedStyle(document.documentElement).getPropertyValue('--span-stt').trim(),
                        progressColor: getComputedStyle(document.documentElement).getPropertyValue('--span-stt-progress').trim()
                    },
                    {
                        waveColor: '#a855f7',      // Purple for channel 1 (bot)
                        progressColor: '#7c3aed'   // Darker purple
                    }
                ]
            });

            this.wavesurfer.load(`/api/sessions/${this.sessionId}/audio`);

            // Event listeners
            this.wavesurfer.on('play', () => { this.playing = true; });
            this.wavesurfer.on('pause', () => { this.playing = false; });
            this.wavesurfer.on('audioprocess', (time) => { this.currentTime = time; });
            this.wavesurfer.on('seek', (progress) => {
                this.currentTime = progress * this.duration;
            });
            this.wavesurfer.on('ready', () => {
                this.duration = this.wavesurfer.getDuration();
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
            this.wavesurfer.on('error', (error) => {
                console.error('Audio loading error:', error);
                this.audioError = true;
            });
        },

        generateTimeline() {
            const timeline = document.getElementById('timeline');
            if (!timeline || !this.duration) return;

            timeline.innerHTML = ''; // Clear existing

            // Show exactly 15 equally-spaced markers
            const markerCount = 15;
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

                label.style.fontSize = '10px';
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
            if (this.wavesurfer) {
                this.wavesurfer.playPause();
            }
        },

        skipBackward(seconds) {
            if (!this.wavesurfer || !this.duration) return;

            const currentTime = this.wavesurfer.getCurrentTime();
            const newTime = Math.max(0, currentTime - seconds);
            const progress = newTime / this.duration;

            this.wavesurfer.seekTo(progress);
        },

        skipForward(seconds) {
            if (!this.wavesurfer || !this.duration) return;

            const currentTime = this.wavesurfer.getCurrentTime();
            const newTime = Math.min(this.duration, currentTime + seconds);
            const progress = newTime / this.duration;

            this.wavesurfer.seekTo(progress);
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
                attrs[attr.key] = attr.value.string_value ||
                                 attr.value.int_value ||
                                 attr.value.double_value ||
                                 attr.value.bool_value;
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
            if (!span || !span.attributes) return '';

            const transcriptAttr = span.attributes.find(attr => attr.key === 'transcript');
            if (!transcriptAttr) return '';

            return transcriptAttr.value.string_value || '';
        },

        getOutputText(span) {
            if (!span || !span.attributes) return '';

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
            if (!attr) return null;

            return attr.value.string_value ||
                   attr.value.int_value ||
                   attr.value.double_value ||
                   attr.value.bool_value;
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

        // Get TTFB (Time to First Byte) value from span attributes
        getTTFB(span) {
            if (!span || !span.attributes) return null;

            const ttfbAttr = span.attributes.find(a => a.key === 'metrics.ttfb');
            if (!ttfbAttr || !ttfbAttr.value.double_value) return null;

            return ttfbAttr.value.double_value;
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
            if (!span || !span.attributes) return null;

            const latencyAttr = span.attributes.find(a => a.key === 'turn.user_bot_latency_seconds');
            if (!latencyAttr || !latencyAttr.value.double_value) return null;

            return latencyAttr.value.double_value;
        },

        // Check if latency is >= 2 seconds (slow response)
        isSlowLatency(span) {
            const latencySeconds = this.getUserBotLatency(span);
            return latencySeconds !== null && latencySeconds >= 2.0;
        },

        // Format user-bot latency value for display with turtle icon if slow
        formatUserBotLatency(span) {
            const latencySeconds = this.getUserBotLatency(span);
            if (latencySeconds === null) return '';

            // Convert seconds to milliseconds and format
            const formattedTime = formatDuration(latencySeconds * 1000);

            if (latencySeconds >= 2.0) {
                return `${formattedTime} ${getIcon('turtle')}`;
            }

            return formattedTime;
        },

        // Get interruption status from span attributes
        wasInterrupted(span) {
            if (!span || !span.attributes) return null;

            const interruptedAttr = span.attributes.find(a => a.key === 'turn.was_interrupted');
            if (!interruptedAttr || interruptedAttr.value.bool_value === undefined) return null;

            return interruptedAttr.value.bool_value;
        },

        hasException(span) {
            if (span.events) {
                return span.events.some(e => e.name === 'exception');
            }
            return false;
        },

        // Format interruption status for display
        formatInterrupted(span) {
            const interrupted = this.wasInterrupted(span);
            if (interrupted === null) return '';

            if (interrupted) {
                return `Yes ${getIcon('interrupted')}`;
            } else {
                return 'No';
            }
        },

        // Format bot chunk text (interrupt icon removed for cleaner display)
        formatBotChunkText(chunk) {
            if (!chunk.botText) return '';
            return chunk.botText;
        },

        // Format bar duration with interruption and slow latency icons if needed
        formatBarDuration(span) {
            if (!span) return '';

            const icons = [
                this.hasException(span) && getIcon('error', ICON_STYLES.small),
                span.name === 'llm' && this.spanHasToolCalls(span) && getIcon('tool', ICON_STYLES.small),
                span.name === 'turn' && this.wasInterrupted(span) && getIcon('interrupted', ICON_STYLES.small),
                span.name === 'turn' && this.isSlowLatency(span) && getIcon('turtle', ICON_STYLES.small),
            ].filter(Boolean);

            return [formatDuration(span.durationMs), ...icons].join(' ');
        },

        // Get all tool calls from the input attribute
        hasToolCalls(msg) {
            return msg.role === 'assistant' && Array.isArray(msg.tool_calls);
        },

        getToolCalls(span) {
            if (!span || span.name !== 'llm') return [];

            const inputValue = this.getAttribute(span, 'input');
            if (!inputValue) return [];

            try {
                const messages = JSON.parse(inputValue);
                if (!Array.isArray(messages)) return [];
                return messages.filter(m => this.hasToolCalls(m)).flatMap(m => m.tool_calls);
            } catch (e) {
                return [];
            }
        },

        spanHasToolCalls(span) {
            return this.getToolCalls(span).length > 0;
        },

        getToolCallNames(span) {
            const toolCalls = this.getToolCalls(span);
            if (toolCalls.length === 0) return '';
            return toolCalls.map(tc => tc.function?.name || 'unknown').join(', ');
        },

        // Format tool calls as JSON
        formatToolCalls(span) {
            const toolCalls = this.getToolCalls(span);
            if (toolCalls.length === 0) return '[]';

            return JSON.stringify(toolCalls, null, 2);
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

            waveformContainer.addEventListener('mousemove', (e) => {
                const rect = waveformContainer.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const percent = x / rect.width;
                const time = percent * this.duration;

                this.hoverMarker.time = time;
                this.hoverMarker.source = 'waveform';
                this.hoverMarker.visible = true;
            });

            waveformContainer.addEventListener('mouseleave', () => {
                if (this.hoverMarker.source === 'waveform') {
                    this.hoverMarker.visible = false;
                }
            });
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

        async reloadAudioIfNotPlaying() {
            if (this.wavesurfer && !this.wavesurfer.isPlaying()) {
                console.log('Reloading audio waveform (synchronized with spans)');
                const audioUrl = `/api/sessions/${this.sessionId}/audio?t=${Date.now()}`;
                this.wavesurfer.load(audioUrl);
            } else if (this.wavesurfer) {
                console.log('Audio is playing, skipping reload');
            }
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
