
    async getPendingEssays(examId = null, page = 1, perPage = 20) {
        const params = new URLSearchParams({ page, per_page: perPage });
        if (examId) params.append('exam_id', examId);
        return this.request('GET', `/grading/pending-essays?${params}`);
    }

    async getGradingStats() {
        return this.request('GET', '/grading/stats');
    }

    async gradeEssay(answerId, pointsEarned, feedback = null) {
        return this.request('POST', '/grading/grade-essay', {
            answer_id: answerId,
            points_earned: pointsEarned,
            feedback
        });
    }

    async batchGradeEssays(grades) {
        return this.request('POST', '/grading/batch-grade', { grades });
    }

    async getAnswerDetail(answerId) {
        return this.request('GET', `/grading/answer/${answerId}`);
    }

    // === ANALYTICS ===

    async getStudentPerformance(studentId) {
        return this.request('GET', `/analytics/student/${studentId}`);
    }

    async getClassPerformance(className, examId = null) {
        const params = new URLSearchParams({ class_name: className });
        if (examId !== null && examId !== undefined && examId !== '') {
            params.append('exam_id', String(examId));
        }
        return this.request('GET', `/analytics/class?${params.toString()}`);
    }

    async getExamClasses(examId) {
        return this.request('GET', `/analytics/exam/${examId}/classes`);
    }

    async getQuestionDifficultyAnalysis(examId) {
        return this.request('GET', `/analytics/exam/${examId}/question-difficulty`);
    }

    async getAssessmentAnalysis(examId, className) {
        const params = new URLSearchParams();
        if (className && typeof className === 'object' && Array.isArray(className.classNames)) {
            params.set('class_names', className.classNames.join(','));
        } else {
            params.set('class_name', className);
        }
        return this.request('GET', `/analytics/exam/${examId}/assessment?${params.toString()}`);
    }

    async getAnalyticsDashboard(days = 7) {
        return this.request('GET', `/analytics/dashboard?days=${days}`);
    }

    // === MONITORING ===

    async getViolationsDashboard(examId = null, dateFrom = null, dateTo = null, options = {}) {
        const params = new URLSearchParams();
        if (examId) params.append('exam_id', examId);
        if (dateFrom) params.append('date_from', dateFrom);
        if (dateTo) params.append('date_to', dateTo);
        if (options && options.summaryOnly) params.append('summary_only', 'true');
        if (options && options.countedOnly) params.append('counted_only', 'true');
        if (options && options.detailLevel) params.append('detail_level', options.detailLevel);
        const query = params.toString();
        return this.request('GET', `/monitoring/violations${query ? `?${query}` : ''}`);
    }

    async getLiveExamStats(examId) {
        return this.request('GET', `/monitoring/exam/${examId}/live-stats`);
    }

    async getExamSessions(examId, status = null, includeRecovery = false) {
        const params = new URLSearchParams();
        if (status) params.append('status', status);
        if (includeRecovery) params.append('include_recovery', 'true');
        const query = params.toString();
        return this.request('GET', `/monitoring/exam/${examId}/sessions${query ? `?${query}` : ''}`);
    }

    async getActiveExams() {
        return this.request('GET', '/monitoring/active-exams');
    }

    async getViolationTypes() {
        return this.request('GET', '/monitoring/violation-types');
    }

    async getRuntimePolicy() {
        return this.request('GET', '/runtime/policy');
    }

    async getOpsSummary() {
        return this.request('GET', '/monitoring/system/ops-summary');
    }

    async setDegradeMode(enabled, reason = 'Manual toggle from monitoring', ttlMinutes = 120) {
        return this.request('POST', '/monitoring/system/degrade-mode', {
            enabled: !!enabled,
            reason,
            ttl_minutes: ttlMinutes
        });
    }

    async getAutoRestartSchedule() {
        return this.request('GET', '/monitoring/system/auto-restart-schedule');
    }

    async setAutoRestartSchedule(payload) {
        return this.request('POST', '/monitoring/system/auto-restart-schedule', payload);
    }

    async runAutoRestartCheck(reason = 'Manual scheduler check', force = true, dryRun = true) {
        return this.request('POST', '/monitoring/system/auto-restart-schedule/check', {
            reason,
            force: !!force,
            dry_run: !!dryRun
        });
    }

    async getResourceMode() {
        return this.request('GET', '/monitoring/system/resource-mode');
    }

    async setResourceMode(mode, reason = 'Manual resource mode update', ttlMinutes = 120) {
        return this.request('POST', '/monitoring/system/resource-mode', {
            mode,
            reason,
            ttl_minutes: ttlMinutes
        });
    }

    async getAutoIntelligenceStatus() {
        return this.request('GET', '/monitoring/system/auto-intelligence');
    }

    async updateAutoIntelligenceControl(payload) {
        return this.request('POST', '/monitoring/system/auto-intelligence', payload);
    }

    async runAutoIntelligence(reason = 'Manual run auto intelligence', force = true, forceHeal = false) {
        return this.request('POST', '/monitoring/system/auto-intelligence/run', {
            reason,
            force: !!force,
            force_heal: !!forceHeal
        });
    }

    async restartSystemSafely(
        reason = 'Restart FULL antar sesi ujian',
        restartBufferMinutes = 30,
        dryRun = false,
        fullRestart = true,
        includeDataServices = true,
        restartTimeoutSeconds = 300
    ) {
        return this.request('POST', '/monitoring/system/restart-safe', {
            reason,
            restart_buffer_minutes: restartBufferMinutes,
            dry_run: !!dryRun,
            full_restart: !!fullRestart,
            include_data_services: !!includeDataServices,
            restart_timeout_seconds: restartTimeoutSeconds
        });
    }

    async getSessionRecoveryStatus(sessionId) {
        return this.request('GET', `/monitoring/sessions/${sessionId}/recovery-status`);
    }

    async resetSessionAfterDisconnect(sessionId, reason = 'Reset sesi karena gangguan koneksi') {
        return this.request('POST', `/monitoring/sessions/${sessionId}/reset`, {
            reason
        });
    }

    async getRecoveryCandidates(examId, limit = 400) {
        const safeLimit = Math.max(50, Math.min(Number(limit || 400), 1000));
        return this.request('GET', `/monitoring/exam/${examId}/recovery-candidates?limit=${safeLimit}`);
    }

    async reopenSessionOverride(sessionId, reason = 'Override pengawas dari Recovery Center', resetViolationCount = true) {
        return this.request('POST', `/monitoring/sessions/${sessionId}/reopen-override`, {
            reason,
            reset_violation_count: !!resetViolationCount
        });
    }

    /**
     * Get session status (for server time sync)
     */
    async getSessionStatus(sessionId) {
        return this.request('GET', `/exams/session/${sessionId}/status`);
    }

    // Generic HTTP helper methods
    async get(endpoint, params = null) {
        let url = endpoint;
        if (params) {
            const queryParams = new URLSearchParams();
            Object.entries(params).forEach(([key, value]) => {
                if (value !== null && value !== undefined && value !== '') {
                    queryParams.append(key, value);
                }
            });
            if (queryParams.toString()) {
                url += (url.includes('?') ? '&' : '?') + queryParams.toString();
            }
        }
        return this.request('GET', url);
    }

    async post(endpoint, data = null) {
        return this.request('POST', endpoint, data);
    }

    async put(endpoint, data = null) {
        return this.request('PUT', endpoint, data);
    }

    async delete(endpoint) {
        return this.request('DELETE', endpoint);
    }

    // === SUBJECTS (BIDANG STUDI) ===

    async getSubjects() {
        return this.request('GET', '/subjects');
    }

    async createSubject(name, description = null) {
        return this.request('POST', '/subjects', { name, description });
    }

    async deleteSubject(id) {
        return this.request('DELETE', `/subjects/${id}`);
    }

    // === EXAM TEMPLATES ===

    async getTemplates(publicOnly = false, page = 1, perPage = 20) {
        const params = new URLSearchParams({
            public_only: publicOnly,
            page,
            per_page: perPage
        });
        return this.request('GET', `/templates/?${params}`);
    }

    async getTemplate(id) {
        return this.request('GET', `/templates/${id}`);
    }

    async createTemplate(templateData) {
        return this.request('POST', '/templates/', templateData);
    }

    async createExamFromTemplate(templateId, examData) {
        return this.request('POST', `/templates/${templateId}/create-exam`, examData);
    }

    async updateTemplate(id, data) {
        return this.request('PUT', `/templates/${id}`, data);
    }

    async deleteTemplate(id) {
        return this.request('DELETE', `/templates/${id}`);
    }

    async saveExamAsTemplate(examId, name, description = null, isPublic = false) {
        // First get the exam with questions
        const exam = await this.request('GET', `/exams/${examId}`);
        const questions = await this.request('GET', `/questions/${examId}/all`);

        // Create template data
        const templateData = {
            name,
            description,
            is_public: isPublic,
            template_data: {
                duration_minutes: exam.duration_minutes,
                passing_score: exam.passing_score,
                max_attempts: exam.max_attempts,
                shuffle_questions: exam.shuffle_questions,
                shuffle_options: exam.shuffle_options,
                show_results: exam.show_results,
                allow_review: exam.allow_review,
                questions: questions
            }
        };

        return this.request('POST', '/templates/', templateData);
    }
}

// Global API instance
// Global API instance
window.api = new ApiClient();
const api = window.api; // Maintain local reference for file internal usage if any
