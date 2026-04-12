function conversationViewMixin() {
    return {
        conversationTurns: [],
        conversationLoading: false,
        conversationError: null,
        timelineItems: [],
        timelineHeight: 0,

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
            const items = [];

            for (const turn of this.conversationTurns) {
                for (const msg of (turn.messages || [])) {
                    items.push({
                        type: 'message',
                        side: msg.role === 'user' ? 'left' : 'right',
                        data: msg,
                        startNs: Number(msg.timestamp),
                        endNs: Number(msg.end_timestamp || msg.timestamp),
                    });
                }

                for (const fc of (turn.function_calls || [])) {
                    items.push({
                        type: 'function_call',
                        side: 'right',
                        data: fc,
                        startNs: Number(fc.start_time_unix_nano),
                        endNs: Number(fc.end_time_unix_nano),
                    });
                }

                for (const evt of (turn.events || [])) {
                    const side = this.isUserEvent(evt) ? 'left' : 'right';
                    items.push({
                        type: 'event',
                        side,
                        data: evt,
                        startNs: Number(evt.time_unix_nano),
                        endNs: Number(evt.time_unix_nano),
                    });
                }

                // TODO: position latency blocks in the timeline
                // For now, latency is omitted to avoid overlap issues
            }

            items.sort((a, b) => a.startNs - b.startNs);

            if (items.length === 0) {
                this.timelineItems = [];
                this.timelineHeight = 0;
                return;
            }

            const originNs = items[0].startNs;
            const BASE_HEIGHT = 100;
            const REF_SEC = 0.3;
            const MIN_BUBBLE_HEIGHT = 60;
            const MIN_EVENT_HEIGHT = 22;
            const ITEM_GAP = 4;

            const nsToY = (ns) => {
                const deltaSec = (ns - originNs) / 1_000_000_000;
                if (deltaSec <= 0) return 0;
                return BASE_HEIGHT * Math.log2(1 + deltaSec / REF_SEC);
            };

            const LABEL_HEIGHT = 24;
            const PADDING = 16;

            for (const item of items) {
                item.rawY = nsToY(item.startNs);
                const endY = nsToY(item.endNs);
                const durationHeight = endY - item.rawY;

                if (item.type === 'message') {
                    const textLen = item.data.content ? item.data.content.length : 0;
                    const estimatedTextHeight = Math.ceil(textLen / 30) * 20 + 24;
                    item.height = estimatedTextHeight + LABEL_HEIGHT + PADDING;
                } else if (item.type === 'function_call') {
                    let attrLines = 2;
                    if (item.data.attributes) {
                        for (const [k, v] of Object.entries(item.data.attributes)) {
                            const lineLen = k.length + String(v).length + 2;
                            attrLines += Math.ceil(lineLen / 25);
                        }
                    }
                    const estimatedHeight = attrLines * 18 + 24;
                    item.height = Math.max(durationHeight, estimatedHeight) + LABEL_HEIGHT + PADDING;
                } else {
                    item.height = MIN_EVENT_HEIGHT;
                }
            }

            const leftTrack = [];
            const rightTrack = [];
            let maxY = 0;

            for (const item of items) {
                const track = item.side === 'left' ? leftTrack : rightTrack;
                let y = item.rawY;

                for (const prev of track) {
                    const prevBottom = prev.y + prev.height + ITEM_GAP;
                    if (y < prevBottom) {
                        y = prevBottom;
                    }
                }

                item.y = y;
                track.push(item);

                const itemBottom = item.y + item.height;
                if (itemBottom > maxY) maxY = itemBottom;
            }

            this.timelineItems = items;
            this.timelineHeight = maxY + 40;
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
