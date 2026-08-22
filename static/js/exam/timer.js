/* exam/timer.js — timer + autosave hooks */


    async initOfflineStorage() {
        try {
            storageManager = new ExamStorageManager();
            await storageManager.init();
            syncWorker = new AnswerSyncWorker(storageManager, () => this.getToken());

            console.log('📦 Offline storage initialized');
        } catch (error) {
            console.warn('Offline storage initialization failed:', error);
        }
    }

    setupAutoSave() {
        const jitter = Math.random() * 5000;
        const intervalMs = this.runtimePolicy.auto_save_interval_ms || 30000;
        setTimeout(() => {
            this.autoSaveInterval = setInterval(() => {
                this.autoSave();
            }, intervalMs);
        }, jitter);
    }

    setupTimer() {
        this.updateTimer();
        this.timerInterval = setInterval(() => {
            this.updateTimer();
        }, 1000);
    }

    async updateTimer() {
        // Skip countdown if exam is paused
        if (this.globallyPaused) {
            return; // Timer frozen during pause
        }

        const now = Date.now() + this.serverTimeOffset;
        const remaining = Math.max(0, this.endTime - now);

        const hours = Math.floor(remaining / (1000 * 60 * 60));
        const minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((remaining % (1000 * 60)) / 1000);

        const timerElement = document.getElementById('timer-value');
        const timerContainer = document.getElementById('timer-container');
        if (timerElement) {
            if (hours > 0) {
                timerElement.textContent = `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            } else {
                timerElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            }

            // Apply state classes to both timer value and container
            timerElement.classList.remove('timer-warning', 'timer-danger');
            if (timerContainer) {
                timerContainer.classList.remove('warning', 'danger');
            }

            if (remaining <= 60000) {
                timerElement.classList.add('timer-danger');
                if (timerContainer) timerContainer.classList.add('danger');
            } else if (remaining <= 300000) {
                timerElement.classList.add('timer-warning');
                if (timerContainer) timerContainer.classList.add('warning');
            }
        }

        this.pushTimerStateToNative(false);

        if (remaining <= 0) {
            clearInterval(this.timerInterval);

            // CRITICAL FIX: Don't await showAlert - it blocks auto-submit!
            // Instead, show non-blocking notification and submit immediately
            console.log('⏰ Timer expired! Auto-submitting exam...');
            showNotification('Waktu ujian telah habis! Mengumpulkan ujian...', 'warning');

            // Submit immediately without confirmation
            this.submitExam(false);
        }
    }

    setupBeforeUnload() {
        window.addEventListener('beforeunload', (e) => {
            this.autoSave();
            e.preventDefault();
            e.returnValue = 'Anda yakin ingin meninggalkan ujian?';
            return e.returnValue;
        });
    }
