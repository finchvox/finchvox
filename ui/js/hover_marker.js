function hoverMarkerMixin() {
    return {
        hoverMarker: {
            visible: false,
            time: 0,
            source: null
        },
        hoveredSpan: null,
        chunkHoveredSpan: null,

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

        showMarkerAtSpan(span) {
            const relativeMs = span.startMs - this.minTime;
            this.hoverMarker.time = relativeMs / 1000;
            this.hoverMarker.source = 'waterfall';
            this.hoverMarker.visible = true;
        },

        hideMarkerFromWaterfall() {
            if (this.hoverMarker.source === 'waterfall') {
                this.hoverMarker.visible = false;
            }
        },

        refreshMarkerPosition() {
            if (this.hoverMarker.visible && this.hoverMarker.source === 'waterfall') {
                const savedTime = this.hoverMarker.time;
                this.hoverMarker.visible = false;
                this.$nextTick(() => {
                    this.hoverMarker.time = savedTime;
                    this.hoverMarker.visible = true;
                });
            }
        },

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

        getMarkerTimeLabel() {
            if (!this.hoverMarker.visible) return '';
            return this.formatTime(this.hoverMarker.time);
        },

        highlightSpan(span) {
            this.hoveredSpan = span;
            this.showMarkerAtSpan(span);
        },

        unhighlightSpan() {
            this.hoveredSpan = null;
            this.hideMarkerFromWaterfall();
        },

        highlightSpanFromChunk(span) {
            this.hoveredSpan = span;
            this.chunkHoveredSpan = span;
            this.showMarkerAtSpan(span);
        },

        unhighlightSpanFromChunk() {
            this.hoveredSpan = null;
            this.chunkHoveredSpan = null;
            this.hideMarkerFromWaterfall();
        },

        handleChunkClick(span) {
            this.selectSpan(span, true);
        }
    };
}
