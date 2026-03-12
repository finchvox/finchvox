function audioPlayerMixin() {
    return {
        wavesurfer: null,
        playing: false,
        currentTime: 0,
        duration: 0,
        audioError: false,

        initAudioPlayer() {
            if (this.wavesurfer) {
                return;
            }

            this.wavesurfer = WaveSurfer.create({
                container: '#waveform',
                waveColor: '#a855f7',
                progressColor: '#7c3aed',
                cursorColor: '#ffffff',
                height: 40,
                barWidth: 2,
                barGap: 1,
                barRadius: 2,
                normalize: true,
                backend: 'WebAudio',
                splitChannels: [
                    {
                        waveColor: getComputedStyle(document.documentElement).getPropertyValue('--span-stt').trim(),
                        progressColor: getComputedStyle(document.documentElement).getPropertyValue('--span-stt-progress').trim()
                    },
                    {
                        waveColor: '#a855f7',
                        progressColor: '#7c3aed'
                    }
                ]
            });

            this.wavesurfer.load(`/api/sessions/${this.sessionId}/audio`);

            this.wavesurfer.on('play', () => { this.playing = true; });
            this.wavesurfer.on('pause', () => { this.playing = false; });
            this.wavesurfer.on('audioprocess', (time) => { this.currentTime = time; });
            this.wavesurfer.on('seek', (progress) => {
                this.currentTime = progress * this.duration;
            });
            this.wavesurfer.on('ready', () => {
                this.duration = this.wavesurfer.getDuration();
                console.log('Audio ready, duration:', this.duration);

                if (this.audioError) {
                    console.log('Audio loaded successfully, clearing error state');
                    this.audioError = false;
                }

                this.generateTimeline();
                this.initWaveformHover();
            });
            this.wavesurfer.on('error', (error) => {
                console.error('Audio loading error:', error);
                this.audioError = true;
            });
        },

        generateTimeline() {
            const timeline = document.getElementById('timeline');
            if (!timeline || !this.duration) return;

            timeline.innerHTML = '';

            const markerCount = 15;
            const interval = this.duration / markerCount;

            timeline.style.display = 'block';
            timeline.style.position = 'relative';
            timeline.style.width = '100%';
            timeline.style.height = '20px';

            for (let i = 0; i <= markerCount; i++) {
                const time = i * interval;
                const percent = (time / this.duration) * 100;

                const marker = document.createElement('div');
                marker.className = 'timeline-marker';
                marker.style.position = 'absolute';
                marker.style.left = `${percent}%`;
                marker.style.height = '20px';

                const tick = document.createElement('div');
                tick.style.position = 'absolute';
                tick.style.left = '0';
                tick.style.bottom = '0';
                tick.style.width = '1px';
                tick.style.height = '3px';
                tick.style.backgroundColor = '#6b7280';

                const label = document.createElement('span');
                label.style.position = 'absolute';
                label.style.left = '0';
                label.style.top = '0';

                if (i === 0) {
                    label.style.transform = 'translateX(0)';
                } else if (i === markerCount) {
                    label.style.transform = 'translateX(-100%)';
                } else {
                    label.style.transform = 'translateX(-50%)';
                }

                label.style.fontSize = '10px';
                label.style.color = '#9ca3af';
                label.style.fontFamily = 'monospace';
                label.textContent = this.formatTimelineLabel(time);

                marker.appendChild(tick);
                marker.appendChild(label);
                timeline.appendChild(marker);
            }
        },

        formatTimelineLabel(seconds) {
            return formatDuration(seconds * 1000, 0);
        },

        togglePlay() {
            if (this.wavesurfer) {
                this.wavesurfer.playPause();
            }
        },

        skipBackward(seconds) {
            if (!this.wavesurfer || !this.duration) return;

            const currentTime = this.wavesurfer.getCurrentTime();
            const newTime = Math.max(0, currentTime - seconds);
            const progress = newTime / this.duration;

            this.wavesurfer.seekTo(progress);
        },

        skipForward(seconds) {
            if (!this.wavesurfer || !this.duration) return;

            const currentTime = this.wavesurfer.getCurrentTime();
            const newTime = Math.min(this.duration, currentTime + seconds);
            const progress = newTime / this.duration;

            this.wavesurfer.seekTo(progress);
        },

        async reloadAudioIfNotPlaying() {
            if (this.wavesurfer && !this.wavesurfer.isPlaying()) {
                console.log('Reloading audio waveform (synchronized with spans)');
                const audioUrl = `/api/sessions/${this.sessionId}/audio?t=${Date.now()}`;
                this.wavesurfer.load(audioUrl);
            } else if (this.wavesurfer) {
                console.log('Audio is playing, skipping reload');
            }
        }
    };
}
