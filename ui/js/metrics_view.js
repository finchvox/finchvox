function metricsViewMixin() {
    return {
        metricsData: null,
        metricsLoading: false,
        metricsError: null,
        // A frozen holder keeps mutable Chart instances outside Alpine's proxies.
        metricsCharts: Object.freeze({}),
        metricsEvents: null,

        async fetchMetrics() {
            if (this.metricsData) return;

            this.metricsLoading = true;
            this.metricsError = null;

            try {
                const response = await fetch(`/api/sessions/${this.sessionId}/metrics`);
                if (!response.ok) {
                    throw new Error(`Failed to fetch metrics: ${response.status}`);
                }
                this.metricsData = await response.json();
            } catch (error) {
                console.error('Error fetching metrics:', error);
                this.metricsError = error.message;
            } finally {
                this.metricsLoading = false;
            }
        },

        shouldLoadMetrics() {
            if (this.selectedView !== 'metrics') return false;
            if (this.metricsData || this.metricsLoading) return false;
            return true;
        },

        async loadMetricsIfNeeded() {
            if (!this.shouldLoadMetrics()) return;
            await this.fetchMetrics();
            this.$nextTick(() => {
                this.initMetricsCharts();
            });
        },

        initMetricsCharts() {
            if (!this.metricsData || !this.metricsData.services) return;

            this.destroyMetricsCharts();
            this.metricsEvents = new AbortController();

            for (const service of this.metricsData.services) {
                const canvas = document.getElementById(`ttfb-chart-${service}`);
                if (!canvas) continue;

                const seriesData = this.metricsData.series[service];
                if (!seriesData || !seriesData.data_points.length) continue;

                canvas.addEventListener('mouseleave', () => this.hideMarkerFromMetrics(),
                    { signal: this.metricsEvents.signal });
                const chart = new Chart(
                    canvas.getContext('2d'),
                    this.createChartConfig(service, seriesData)
                );
                this.metricsCharts = Object.freeze({ ...this.metricsCharts, [service]: chart });
            }

            this.initUserBotLatencyChart();
        },

        initUserBotLatencyChart() {
            const latencyData = this.metricsData?.user_bot_latency;
            if (!latencyData || !latencyData.data_points?.length) return;

            const canvas = document.getElementById('user-bot-latency-chart');
            if (!canvas) return;

            this.metricsEvents ??= new AbortController();
            canvas.addEventListener('mouseleave', () => this.hideMarkerFromMetrics(),
                { signal: this.metricsEvents.signal });
            const chart = new Chart(
                canvas.getContext('2d'),
                this.createLatencyChartConfig(latencyData)
            );
            this.metricsCharts = Object.freeze({ ...this.metricsCharts, user_bot_latency: chart });
        },

        createChartConfig(service, seriesData) {
            const color = this.getServiceColor(service);
            const dataPoints = seriesData.data_points.map(p => ({
                x: p.relative_time_ms / 1000,
                y: p.ttfb_ms,
                span_id: p.span_id
            }));

            return {
                type: 'line',
                data: {
                    datasets: [{
                        label: `${service.toUpperCase()} TTFB`,
                        data: dataPoints,
                        borderColor: color,
                        backgroundColor: color + '33',
                        borderWidth: 2,
                        pointRadius: 2,
                        pointHoverRadius: 3,
                        pointBackgroundColor: color,
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 1,
                        tension: 0.1,
                        fill: true
                    }]
                },
                options: this.createChartOptions(service, color)
            };
        },

        createChartOptions(service, color) {
            return {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'nearest', axis: 'x', intersect: false },
                onClick: (event, elements) => this.handleChartClick(service, elements),
                onHover: (event, elements) => this.handleChartHover(service, elements),
                plugins: {
                    legend: { display: false },
                    tooltip: this.createTooltipConfig(color)
                },
                scales: {
                    x: this.createXAxisConfig(),
                    y: this.createYAxisConfig()
                }
            };
        },

        createTooltipConfig(color) {
            return {
                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                titleColor: '#ffffff',
                bodyColor: '#ffffff',
                borderColor: color,
                borderWidth: 1,
                padding: 10,
                displayColors: false,
                callbacks: {
                    title: (items) => {
                        if (!items.length) return '';
                        return `Time: ${this.formatMetricsTime(items[0].parsed.x)}`;
                    },
                    label: (context) => `TTFB: ${context.parsed.y.toFixed(1)}ms`
                }
            };
        },

        createXAxisConfig() {
            return {
                type: 'linear',
                title: { display: false },
                ticks: {
                    color: 'rgba(255, 255, 255, 0.5)',
                    font: { size: 12 * window.FinchvoxPreferences.textScale(), family: 'monospace' },
                    callback: (value) => this.formatMetricsTime(value)
                },
                grid: { color: 'rgba(255, 255, 255, 0.05)' }
            };
        },

        createYAxisConfig() {
            return {
                title: {
                    display: true,
                    text: 'Time (ms)',
                    color: 'rgba(255, 255, 255, 0.5)',
                    font: { size: 14 * window.FinchvoxPreferences.textScale() }
                },
                ticks: {
                    color: 'rgba(255, 255, 255, 0.5)',
                    font: { size: 14 * window.FinchvoxPreferences.textScale(), family: 'monospace' }
                },
                grid: { color: 'rgba(255, 255, 255, 0.05)' },
                beginAtZero: true
            };
        },

        handleChartClick(service, elements) {
            if (!elements || elements.length === 0) return;

            const dataIndex = elements[0].index;
            const dataPoint = this.metricsData.series[service].data_points[dataIndex];
            if (!dataPoint) return;

            const span = this.spans.find(s => s.span_id_hex === dataPoint.span_id);
            if (span) {
                this.selectSpan(span, true);
            }
        },

        handleChartHover(service, elements) {
            if (!elements || elements.length === 0) {
                return;
            }

            const dataIndex = elements[0].index;
            const dataPoint = this.metricsData.series[service].data_points[dataIndex];
            if (!dataPoint) return;

            this.showMarkerFromMetrics(dataPoint.relative_time_ms / 1000);
        },

        showMarkerFromMetrics(timeSeconds) {
            this.hoverMarker.time = timeSeconds;
            this.hoverMarker.source = 'metrics';
            this.hoverMarker.visible = true;
        },

        hideMarkerFromMetrics() {
            if (this.hoverMarker.source === 'metrics') {
                this.hoverMarker.visible = false;
            }
        },

        // Chart colours come from the theme (--chart-* in app.css). They must be
        // #rrggbb, because the fill appends an alpha suffix ("33").
        getServiceColor(service) {
            const token = window.FinchvoxPreferences.cssToken;
            const fallback = token('--chart-default', '#6b7280');
            return ['stt', 'llm', 'tts'].includes(service) ? token(`--chart-${service}`, fallback) : fallback;
        },

        createLatencyChartConfig(seriesData) {
            const color = window.FinchvoxPreferences.cssToken('--chart-latency', '#10b981');
            const dataPoints = seriesData.data_points.map(p => ({
                x: p.relative_time_ms / 1000,
                y: p.latency_ms,
                span_id: p.span_id
            }));

            return {
                type: 'line',
                data: {
                    datasets: [{
                        label: 'Latency',
                        data: dataPoints,
                        borderColor: color,
                        backgroundColor: color + '33',
                        borderWidth: 2,
                        pointRadius: 2,
                        pointHoverRadius: 3,
                        pointBackgroundColor: color,
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 1,
                        tension: 0.1,
                        fill: true
                    }]
                },
                options: this.createLatencyChartOptions(color)
            };
        },

        createLatencyChartOptions(color) {
            return {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'nearest', axis: 'x', intersect: false },
                onClick: (event, elements) => this.handleLatencyChartClick(elements),
                onHover: (event, elements) => this.handleLatencyChartHover(elements),
                plugins: {
                    legend: { display: false },
                    tooltip: this.createLatencyTooltipConfig(color)
                },
                scales: {
                    x: this.createXAxisConfig(),
                    y: this.createYAxisConfig()
                }
            };
        },

        createLatencyTooltipConfig(color) {
            return {
                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                titleColor: '#ffffff',
                bodyColor: '#ffffff',
                borderColor: color,
                borderWidth: 1,
                padding: 10,
                displayColors: false,
                callbacks: {
                    title: (items) => {
                        if (!items.length) return '';
                        return `Time: ${this.formatMetricsTime(items[0].parsed.x)}`;
                    },
                    label: (context) => `Latency: ${context.parsed.y.toFixed(1)}ms`
                }
            };
        },

        handleLatencyChartClick(elements) {
            if (!elements || elements.length === 0) return;

            const dataIndex = elements[0].index;
            const dataPoint = this.metricsData.user_bot_latency.data_points[dataIndex];
            if (!dataPoint) return;

            const span = this.spans.find(s => s.span_id_hex === dataPoint.span_id);
            if (span) {
                this.selectSpan(span, true);
            }
        },

        handleLatencyChartHover(elements) {
            if (!elements || elements.length === 0) {
                return;
            }

            const dataIndex = elements[0].index;
            const dataPoint = this.metricsData.user_bot_latency.data_points[dataIndex];
            if (!dataPoint) return;

            this.showMarkerFromMetrics(dataPoint.relative_time_ms / 1000);
        },

        getUserBotLatencyStats() {
            if (!this.metricsData || !this.metricsData.user_bot_latency) {
                return null;
            }
            return this.metricsData.user_bot_latency.stats;
        },

        selectMetricsSpan(spanId) {
            const span = this.spans.find(s => s.span_id_hex === spanId);
            if (span) this.selectSpan(span, true);
        },

        getWorstEventLoopBlockMs() {
            const blocks = this.metricsData?.event_loop_blocks || [];
            return blocks.reduce((worst, block) => Math.max(worst, block.duration_ms), 0);
        },

        usageAmounts(row) {
            const seconds = new Set(['audio_duration', 'session_duration']);
            return Object.entries(row.amounts || {}).map(([key, value]) => ({
                label: key.replaceAll('_', ' '),
                value: seconds.has(key) ? `${Number(value).toFixed(1)} s` : Number(value).toLocaleString()
            }));
        },

        formatMetricsTime(seconds) {
            return formatDuration(seconds * 1000, 0);
        },

        destroyMetricsCharts() {
            this.metricsEvents?.abort();
            this.metricsEvents = null;
            Object.values(this.metricsCharts).forEach(chart => {
                if (chart) chart.destroy();
            });
            this.metricsCharts = Object.freeze({});
        },

        getMetricsStats(service) {
            if (!this.metricsData || !this.metricsData.series[service]) {
                return null;
            }
            return this.metricsData.series[service].stats;
        },

        formatStatValue(value) {
            if (value === undefined || value === null) return '-';
            return Math.round(value);
        }
    };
}
