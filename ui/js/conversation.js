function conversationViewMixin() {
    return {
        conversationMessages: [],
        conversationEvents: [],
        conversationSource: null,
        conversationLoading: false,
        conversationError: null,

        async fetchConversation() {
            this.conversationLoading = true;
            this.conversationError = null;

            try {
                const response = await fetch(`/api/sessions/${this.sessionId}/conversation`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);

                const data = await response.json();
                this.conversationMessages = data.messages || [];
                this.conversationEvents = data.events || [];
                this.conversationSource = data.source || null;
            } catch (error) {
                console.error('Failed to load conversation:', error);
                this.conversationError = error.message;
            } finally {
                this.conversationLoading = false;
            }
        },

        formatConversationTime(timestamp) {
            if (!timestamp || !this.minTime) return '';
            const messageMs = Number(timestamp) / 1_000_000;
            const relativeMs = messageMs - this.minTime;
            return formatDuration(relativeMs);
        },

        seekToMessage(message) {
            if (!message?.timestamp || !this.minTime) return;

            const messageMs = Number(message.timestamp) / 1_000_000;

            const player = this.getAudioPlayer();
            if (player && this.duration) {
                const isPlaying = player.isPlaying();
                if (!isPlaying) {
                    const audioTime = (messageMs - this.minTime) / 1000;
                    const progress = audioTime / this.duration;
                    player.seekTo(Math.max(0, Math.min(1, progress)));
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

        loadConversationIfNeeded() {
            if (this.selectedView === 'conversation' && this.conversationMessages.length === 0) {
                this.fetchConversation();
            }
        }
    };
}
