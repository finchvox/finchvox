function tracePanelViewMixin() {
    const TRACE_PANEL_WIDTH_STORAGE_KEY = 'finchvox.tracePanel.width';
    const DEFAULT_TRACE_PANEL_WIDTH_PX = 400;
    const MIN_TRACE_PANEL_WIDTH_PX = 320;
    const MAX_TRACE_PANEL_WIDTH_PX = 900;

    return {
        tracePanelWidth: DEFAULT_TRACE_PANEL_WIDTH_PX,
        tracePanelIsResizing: false,
        _tracePanelResizeCleanup: null,
        _tracePanelPrevBodyStyle: null,
        _tracePanelWindowResizeHandler: null,

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

        _saveBodyStyleForResize() {
            this._tracePanelPrevBodyStyle = {
                userSelect: document.body.style.userSelect,
                cursor: document.body.style.cursor
            };
            document.body.style.userSelect = 'none';
            document.body.style.cursor = 'col-resize';
        },

        _restoreBodyStyleAfterResize() {
            if (this._tracePanelPrevBodyStyle) {
                document.body.style.userSelect = this._tracePanelPrevBodyStyle.userSelect ?? '';
                document.body.style.cursor = this._tracePanelPrevBodyStyle.cursor ?? '';
            }
            this._tracePanelPrevBodyStyle = null;
        },

        _finishTracePanelResize() {
            if (!this.tracePanelIsResizing) return;
            this.tracePanelIsResizing = false;
            this.setTracePanelWidth(this.tracePanelWidth, { persist: true });
            this._restoreBodyStyleAfterResize();
            if (this._tracePanelResizeCleanup) {
                this._tracePanelResizeCleanup();
                this._tracePanelResizeCleanup = null;
            }
        },

        _shouldIgnoreResizeEvent(event) {
            if (!event) return true;
            if (event.pointerType === 'mouse' && event.button !== 0) return true;
            if (this._tracePanelResizeCleanup) return true;
            return false;
        },

        _getViewportWidth() {
            return document.documentElement?.clientWidth || window.innerWidth || 0;
        },

        _trySetPointerCapture(event) {
            try {
                event.target?.setPointerCapture?.(event.pointerId);
            } catch {
            }
        },

        startTracePanelResize(event) {
            if (this._shouldIgnoreResizeEvent(event)) return;

            this.tracePanelIsResizing = true;
            this._saveBodyStyleForResize();

            const updateFromPointer = (clientX) => {
                const desiredWidth = this._getViewportWidth() - clientX;
                this.setTracePanelWidth(desiredWidth, { persist: false });
            };

            const onMove = (e) => updateFromPointer(e.clientX);
            const finish = () => this._finishTracePanelResize();

            document.addEventListener('pointermove', onMove);
            document.addEventListener('pointerup', finish, { once: true });
            document.addEventListener('pointercancel', finish, { once: true });

            this._tracePanelResizeCleanup = () => {
                document.removeEventListener('pointermove', onMove);
            };

            this._trySetPointerCapture(event);
            updateFromPointer(event.clientX);
        }
    };
}
