function sessionsListApp() {
    return {
        sessions: [],
        dataDir: '',
        showUploadSection: false,
        uploadFile: null,
        uploading: false,
        uploadError: null,

        currentPage: 1,
        totalCount: 0,
        totalPages: 1,
        pageSize: 50,
        hasPreviousPage: false,
        hasNextPage: false,
        loading: false,

        initialized: false,
        requestToken: 0,

        async init() {
            if (this.initialized) return;
            this.initialized = true;
            await this.loadSessions();
        },

        applySessionData(data) {
            this.sessions = data.sessions;
            this.dataDir = data.data_dir;
            this.totalCount = data.total_count;
            this.totalPages = data.total_pages;
            this.pageSize = data.page_size;
            this.currentPage = data.page;
            this.hasPreviousPage = data.has_previous_page;
            this.hasNextPage = data.has_next_page;
        },

        async loadSessions() {
            if (this.loading) return;

            this.loading = true;
            const token = ++this.requestToken;

            try {
                const response = await fetch(`/api/sessions?page=${this.currentPage}`);
                if (token !== this.requestToken) return;
                this.applySessionData(await response.json());
            } catch (error) {
                console.error('Failed to load sessions:', error);
            } finally {
                if (token === this.requestToken) this.loading = false;
            }
        },

        isValidPageChange(page) {
            return page >= 1 && page <= this.totalPages && page !== this.currentPage;
        },

        async goToPage(page) {
            if (!this.isValidPageChange(page)) return;
            this.currentPage = page;
            await this.loadSessions();
        },

        async previousPage() {
            await this.goToPage(this.currentPage - 1);
        },

        async nextPage() {
            await this.goToPage(this.currentPage + 1);
        },

        formatSessionCount(count) {
            const suffix = count !== 1 ? 's' : '';
            return `${count} session${suffix}`;
        },

        get showingRangeText() {
            if (this.loading) return 'Loading...';
            if (this.totalCount === 0) return '0 sessions';
            if (this.totalPages === 1) return this.formatSessionCount(this.totalCount);

            const start = (this.currentPage - 1) * this.pageSize + 1;
            const end = Math.min(this.currentPage * this.pageSize, this.totalCount);
            return `Showing ${start}-${end} of ${this.totalCount} sessions`;
        },

        async uploadSession() {
            if (!this.uploadFile) return;

            this.uploading = true;
            this.uploadError = null;

            try {
                const formData = new FormData();
                formData.append('file', this.uploadFile);

                const response = await fetch('/api/sessions/upload', {
                    method: 'POST',
                    body: formData
                });

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
