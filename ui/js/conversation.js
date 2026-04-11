function conversationViewMixin() {
    return {
        conversationTurns: [],
        conversationLoading: false,
        conversationError: null,

        async fetchConversation() {
            this.conversationLoading = true;
            this.conversationError = null;

            try {
                const response = await fetch(`/api/sessions/${this.sessionId}/conversation`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);

                const data = await response.json();
                this.conversationTurns = data.turns;
            } catch (error) {
                console.error('Failed to load conversation:', error);
                this.conversationError = error.message;
            } finally {
                this.conversationLoading = false;
            }
        },

        formatEventTime(timeUnixNano) {
            if (!timeUnixNano || !this.minTime) return '';
            const ms = Number(timeUnixNano) / 1_000_000;
            const relativeMs = ms - this.minTime;
            return formatDuration(relativeMs);
        },

        seekToMessage(message) {
            if (!message?.timestamp || !this.minTime) return;

            const messageMs = Number(message.timestamp) / 1_000_000;

            if (this.wavesurfer && this.duration) {
                const isPlaying = this.wavesurfer.isPlaying();
                if (!isPlaying) {
                    const audioTime = (messageMs - this.minTime) / 1000;
                    const progress = audioTime / this.duration;
                    this.wavesurfer.seekTo(Math.max(0, Math.min(1, progress)));
                    this.currentTime = audioTime;
                }
            }

            this.hoverMarker.time = (messageMs - this.minTime) / 1000;
            this.hoverMarker.source = 'conversation';
            this.hoverMarker.visible = true;
        },

        hideConversationMarker() {
            if (this.hoverMarker.source === 'conversation') {
                this.hoverMarker.visible = false;
            }
        },

        formatLatencyRow(latency) {
            if (!latency) return '';
            const order = [
                ['turn.user_turn_seconds', 'user_turn_seconds'],
                ['stt metrics.ttfb', 'stt_ttfb'],
                ['llm metrics.ttfb', 'llm_ttfb'],
                ['function_call_seconds', 'function_call_seconds'],
                ['turn.text_aggregation_seconds', 'text_aggregation_seconds'],
                ['tts metrics.ttfb', 'tts_ttfb'],
                ['turn.user_bot_latency_seconds', 'user_bot_latency_seconds'],
            ];
            const parts = [];
            for (const [label, key] of order) {
                if (latency[key] != null) {
                    const ms = (latency[key] * 1000).toFixed(0);
                    parts.push(`${label}: ${ms}ms`);
                }
            }
            return parts.join(' | ');
        },

        formatTurnLatencyMs(seconds) {
            if (seconds == null) return '';
            const ms = (seconds * 1000).toFixed(0);
            return `${ms}ms`;
        },

        loadConversationIfNeeded() {
            if (this.selectedView === 'conversation' && this.conversationTurns.length === 0) {
                this.fetchConversation();
            }
        }
    };
}
