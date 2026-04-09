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

function spanFormattingMixin() {
    return {
        formatTime(seconds) {
            if (!seconds) return formatDuration(0);
            return formatDuration(seconds * 1000);
        },

        formatSpanDuration(span) {
            if (!span) return '';
            return formatDuration(span.durationMs);
        },

        formatRelativeStartTime(span) {
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

        getAttribute(span, key) {
            if (!span || !span.attributes) return null;
            const attr = span.attributes.find(a => a.key === key);
            if (!attr) return null;
            return attr.value.string_value ||
                   attr.value.int_value ||
                   attr.value.double_value ||
                   attr.value.bool_value;
        },

        hasAttribute(span, key) {
            return this.getAttribute(span, key) !== null;
        },

        formatAttributeValue(span, key) {
            const value = this.getAttribute(span, key);
            if (value === null) return '';
            try {
                const parsed = JSON.parse(value);
                return JSON.stringify(parsed, null, 2);
            } catch (e) {
                return value;
            }
        },

        getTTFB(span) {
            if (!span || !span.attributes) return null;
            const ttfbAttr = span.attributes.find(a => a.key === 'metrics.ttfb');
            if (!ttfbAttr || !ttfbAttr.value.double_value) return null;
            return ttfbAttr.value.double_value;
        },

        formatTTFB(span) {
            const ttfbSeconds = this.getTTFB(span);
            if (ttfbSeconds === null) return '';
            return formatDuration(ttfbSeconds * 1000);
        },

        getTextAggregation(span) {
            if (!span || !span.attributes) return null;
            const attr = span.attributes.find(a => a.key === 'turn.text_aggregation_seconds');
            if (!attr || !attr.value.double_value) return null;
            return attr.value.double_value;
        },

        formatTextAggregation(span) {
            const seconds = this.getTextAggregation(span);
            if (seconds === null) return '';
            return formatDuration(seconds * 1000);
        },

        getUserBotLatency(span) {
            if (!span || !span.attributes) return null;
            const latencyAttr = span.attributes.find(a => a.key === 'turn.user_bot_latency_seconds');
            if (!latencyAttr || !latencyAttr.value.double_value) return null;
            return latencyAttr.value.double_value;
        },

        isSlowLatency(span) {
            const latencySeconds = this.getUserBotLatency(span);
            return latencySeconds !== null && latencySeconds >= 2.0;
        },

        formatUserBotLatency(span) {
            const latencySeconds = this.getUserBotLatency(span);
            if (latencySeconds === null) return '';
            const formattedTime = formatDuration(latencySeconds * 1000);
            if (latencySeconds >= 2.0) {
                return `${formattedTime} ${getIcon('turtle')}`;
            }
            return formattedTime;
        },

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

        formatInterrupted(span) {
            const interrupted = this.wasInterrupted(span);
            if (interrupted === null) return '';
            if (interrupted) {
                return `Yes ${getIcon('interrupted')}`;
            } else {
                return 'No';
            }
        },

        formatBotChunkText(chunk) {
            if (!chunk.botText) return '';
            return chunk.botText;
        },

        _getSpanIcons(span) {
            const icons = [];
            if (this.hasException(span)) icons.push(getIcon('error', ICON_STYLES.small));
            if (span.name === 'llm' && this.spanHasToolCalls(span)) icons.push(getIcon('tool', ICON_STYLES.small));
            if (span.name === 'turn' && this.wasInterrupted(span)) icons.push(getIcon('interrupted', ICON_STYLES.small));
            if (span.name === 'turn' && this.isSlowLatency(span)) icons.push(getIcon('turtle', ICON_STYLES.small));
            return icons;
        },

        formatBarDuration(span) {
            if (!span) return '';
            return [formatDuration(span.durationMs), ...this._getSpanIcons(span)].join(' ');
        },

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

        formatToolCalls(span) {
            const toolCalls = this.getToolCalls(span);
            if (toolCalls.length === 0) return '[]';
            return JSON.stringify(toolCalls, null, 2);
        },

        getRawSpanJSON(span) {
            if (!span) return '{}';
            const { startMs, endMs, durationMs, depth, children, childCount, ...rawSpan } = span;
            return JSON.stringify(rawSpan, null, 2);
        },

        async copySpanToClipboard() {
            if (!this.selectedSpan) return;
            try {
                const spanJSON = this.getRawSpanJSON(this.selectedSpan);
                await navigator.clipboard.writeText(spanJSON);
                this.spanCopied = true;
                setTimeout(() => {
                    this.spanCopied = false;
                }, 1500);
            } catch (err) {
                console.error('Failed to copy span:', err);
            }
        }
    };
}
