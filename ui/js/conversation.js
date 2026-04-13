function conversationViewMixin() {
    return {
        conversationTurns: [],
        conversationLoading: false,
        conversationError: null,
        timelineTurns: [],

        async fetchConversation() {
            this.conversationLoading = true;
            this.conversationError = null;

            try {
                const response = await fetch(`/api/sessions/${this.sessionId}/conversation`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);

                const data = await response.json();
                this.conversationTurns = data.turns;
                this.buildTimeline();
            } catch (error) {
                console.error('Failed to load conversation:', error);
                this.conversationError = error.message;
            } finally {
                this.conversationLoading = false;
            }
        },

        buildTimeline() {
            this.timelineTurns = this.conversationTurns.map(turn => {
                const items = [];

                for (const msg of (turn.messages || [])) {
                    items.push({
                        type: 'message',
                        side: msg.role === 'user' ? 'left' : 'right',
                        data: msg,
                        timestamp: Number(msg.timestamp),
                        latency: null,
                    });
                }

                for (const fc of (turn.function_calls || [])) {
                    items.push({
                        type: 'function_call',
                        side: 'right',
                        data: fc,
                        timestamp: Number(fc.start_time_unix_nano),
                    });
                }

                for (const evt of (turn.events || [])) {
                    items.push({
                        type: 'event',
                        side: this.isUserEvent(evt) ? 'left' : 'right',
                        data: evt,
                        timestamp: Number(evt.time_unix_nano),
                    });
                }

                items.sort((a, b) => a.timestamp - b.timestamp);

                if (turn.latency) {
                    const agentMsg = items.find(i => i.type === 'message' && i.data.role === 'assistant');
                    if (agentMsg) {
                        agentMsg.latency = turn.latency;
                    }
                }

                return {
                    turnNumber: turn.turn_number,
                    items,
                };
            });
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

        getLatencyMetrics(latency) {
            if (!latency) return [];
            const order = [
                ['user_turn', 'user_turn_seconds'],
                ['stt ttfb', 'stt_ttfb'],
                ['llm ttfb', 'llm_ttfb'],
                ['function_call', 'function_call_seconds'],
                ['text_aggregation', 'text_aggregation_seconds'],
                ['tts ttfb', 'tts_ttfb'],
                ['user\u2192bot', 'user_bot_latency_seconds'],
            ];
            const metrics = [];
            for (const [label, key] of order) {
                if (latency[key] != null) {
                    const ms = (latency[key] * 1000).toFixed(0);
                    metrics.push({ label, value: `${ms}ms` });
                }
            }
            return metrics;
        },

        isUserEvent(e) {
            return e.name.startsWith('vad_user') ||
                e.name === 'user_started_speaking' ||
                e.name === 'user_stopped_speaking';
        },

        getFunctionCallAttributes(fc) {
            if (!fc || !fc.attributes) return [];
            return Object.entries(fc.attributes).map(([key, value]) => ({
                key,
                value: String(value),
            }));
        },

        loadConversationIfNeeded() {
            if (this.selectedView === 'conversation' && this.conversationTurns.length === 0) {
                this.fetchConversation();
            }
        }
    };
}
