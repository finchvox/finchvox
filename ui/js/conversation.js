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
                const turns = data.turns;
                for (let i = 0; i < turns.length - 1; i++) {
                    const postEvents = this.getPostInterruptionUserEvents(turns[i].events);
                    if (postEvents.length) {
                        turns[i + 1].carriedUserEvents = postEvents;
                    }
                }
                this.conversationTurns = turns;
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

        getChronologicalItems(turn) {
            const items = [];

            for (const msg of (turn.messages || [])) {
                items.push({
                    type: 'message',
                    data: msg,
                    timestamp: Number(msg.timestamp),
                });
            }

            for (const fc of (turn.function_calls || [])) {
                items.push({
                    type: 'function_call',
                    data: fc,
                    timestamp: Number(fc.start_time_unix_nano),
                });
            }

            items.sort((a, b) => a.timestamp - b.timestamp);

            if (turn.latency) {
                let insertIndex = 0;
                for (let i = 0; i < items.length; i++) {
                    if (items[i].type === 'message' && items[i].data.role === 'user') {
                        insertIndex = i + 1;
                    } else {
                        break;
                    }
                }
                items.splice(insertIndex, 0, {
                    type: 'latency',
                    data: turn.latency,
                    timestamp: 0,
                });
            }

            let lastUserIdx = -1;
            let lastAssistantIdx = -1;
            for (let i = 0; i < items.length; i++) {
                if (items[i].type === 'message') {
                    if (items[i].data.role === 'user') lastUserIdx = i;
                    if (items[i].data.role === 'assistant') lastAssistantIdx = i;
                }
            }
            if (lastUserIdx >= 0) items[lastUserIdx].isLastUser = true;
            if (lastAssistantIdx >= 0) items[lastAssistantIdx].isLastAssistant = true;

            if (lastUserIdx < 0 && turn.events) {
                const preEvents = this.getPreInterruptionUserEvents(turn.events);
                if (preEvents.length) {
                    const firstEventTs = Number(preEvents[0].time_unix_nano);
                    let insertAt = items.length;
                    for (let i = 0; i < items.length; i++) {
                        if (items[i].timestamp > firstEventTs) {
                            insertAt = i;
                            break;
                        }
                    }
                    items.splice(insertAt, 0, {
                        type: 'user_events',
                        data: preEvents,
                        timestamp: firstEventTs,
                    });
                }
            }

            if (turn.carriedUserEvents && turn.carriedUserEvents.length) {
                items.unshift({
                    type: 'user_events',
                    data: turn.carriedUserEvents,
                    timestamp: Number(turn.carriedUserEvents[0].time_unix_nano),
                });
            }

            return items;
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
                ['user→bot', 'user_bot_latency_seconds'],
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

        getUserEvents(events) {
            if (!events) return [];
            return events.filter(e => this.isUserEvent(e));
        },

        getPreInterruptionUserEvents(events) {
            if (!events) return [];
            const lastInterruption = [...events].reverse().find(e => e.name === 'interruption');
            if (!lastInterruption) return events.filter(e => this.isUserEvent(e));
            const cutoffMs = Math.floor(Number(lastInterruption.time_unix_nano) / 1_000_000);
            return events.filter(e => this.isUserEvent(e) && Math.floor(Number(e.time_unix_nano) / 1_000_000) < cutoffMs);
        },

        getPostInterruptionUserEvents(events) {
            if (!events) return [];
            const lastInterruption = [...events].reverse().find(e => e.name === 'interruption');
            if (!lastInterruption) return [];
            const cutoffMs = Math.floor(Number(lastInterruption.time_unix_nano) / 1_000_000);
            return events.filter(e => this.isUserEvent(e) && Math.floor(Number(e.time_unix_nano) / 1_000_000) >= cutoffMs);
        },

        getBotEvents(events) {
            if (!events) return [];
            return events.filter(e => !this.isUserEvent(e));
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
