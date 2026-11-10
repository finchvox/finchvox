function sessionsListApp() {
    return {
        sessions: [],
        dataDir: '',
        showUploadSection: false,
        uploadFile: null,
        uploading: false,
        uploadError: null,
        maxUploadBytes: null,
        // Reactive, so start times re-render when the time format changes in Settings.
        hour12: window.FinchvoxPreferences.hour12(),

        // One page of sessions at a time; the totals cover every session.
        currentPage: 1,
        totalPages: 1,
        totalCount: 0,
        pageSize: 50,
        hasPreviousPage: false,
        hasNextPage: false,
        totals: { sessions: 0, livekit: 0, errors: 0 },
        loading: false,
        // Drops a slow answer for an earlier page that arrives after a newer one.
        requestToken: 0,

        async init() {
            window.addEventListener(window.FinchvoxPreferences.CHANGE_EVENT, event => {
                this.hour12 = event.detail.timeFormat === '12h';
            });
            await this.loadSessions();
        },

        formatStart(timestamp) {
            return formatDate(timestamp, this.hour12);
        },

        async loadSessions() {
            const token = ++this.requestToken;
            this.loading = true;
            try {
                const response = await fetch(`/api/sessions?page=${this.currentPage}`);
                const data = await response.json();
                if (token !== this.requestToken) return;
                this.applySessionData(data);
            } catch (error) {
                console.error('Failed to load sessions:', error);
            } finally {
                if (token === this.requestToken) this.loading = false;
            }
        },

        applySessionData(data) {
            this.sessions = data.sessions || [];
            this.dataDir = data.data_dir || '';
            this.maxUploadBytes = data.max_upload_bytes || null;
            this.currentPage = data.page || 1;
            this.totalPages = data.total_pages || 1;
            this.totalCount = data.total_count || 0;
            this.pageSize = data.page_size || this.pageSize;
            this.hasPreviousPage = Boolean(data.has_previous_page);
            this.hasNextPage = Boolean(data.has_next_page);
            this.totals = data.totals || { sessions: this.sessions.length, livekit: 0, errors: 0 };
        },

        async goToPage(page) {
            if (page < 1 || page > this.totalPages || page === this.currentPage) return;
            this.currentPage = page;
            await this.loadSessions();
        },

        // "Recent sessions", or the range shown when there is more than one page.
        pageCaption() {
            if (this.totalPages <= 1) return 'Recent sessions';
            const start = (this.currentPage - 1) * this.pageSize + 1;
            const end = Math.min(this.currentPage * this.pageSize, this.totalCount);
            return `Sessions ${start}–${end} of ${this.totalCount}`;
        },

        uploadTooLargeMessage() {
            const limit = this.maxUploadBytes
                ? `the ${Math.round(this.maxUploadBytes / (1024 * 1024))} MB upload limit`
                : 'the upload limit';
            return `This file is larger than ${limit}. Restart Finchvox with a higher --max-upload-mb to allow it.`;
        },

        async uploadSession() {
            if (!this.uploadFile) return;

            // Checked here too because the server stops reading an oversized
            // upload, which browsers can report as a network error.
            if (this.maxUploadBytes && this.uploadFile.size > this.maxUploadBytes) {
                this.uploadError = this.uploadTooLargeMessage();
                return;
            }

            this.uploading = true;
            this.uploadError = null;

            try {
                const formData = new FormData();
                formData.append('file', this.uploadFile);

                const response = await fetch('/api/sessions/upload', {
                    method: 'POST',
                    body: formData
                });

                if (response.status === 413) {
                    throw new Error(this.uploadTooLargeMessage());
                }

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || 'Upload failed');
                }

                window.location.href = `/sessions/${data.session_id}`;
            } catch (error) {
                this.uploadError = error.message;
            } finally {
                this.uploading = false;
            }
        },

        formatDuration(milliseconds) {
            if (!milliseconds) return '-';
            return formatDuration(milliseconds, 0);
        },

        formatCount(count) {
            return (count && count > 0) ? count.toLocaleString() : '—';
        }
    };
}
