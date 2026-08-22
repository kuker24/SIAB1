    // Auth endpoints
    async login(username, password) {
        const result = await this.request('POST', '/auth/signin', { username, password });
        this.setToken(result.access_token);
        localStorage.setItem('user', JSON.stringify(result.user));
        return result;
    }

    async getMe() {
        return this.request('GET', '/auth/me');
    }

    async register(userData) {
        return this.request('POST', '/auth/register', userData);
    }

    // Users endpoints
    async getUsers(params = null) {
        return this.get('/users', params);
    }

    async getUser(id) {
        return this.request('GET', `/users/${id}`);
    }

    async createUser(userData) {
        // Use standard POST /users endpoint for single user creation
        // This supports full validation and returns the complete user object
        return this.request('POST', '/users', userData);
    }

    async updateUser(id, userData) {
        return this.request('PUT', `/users/${id}`, userData);
    }

    async deleteUser(id) {
        return this.request('DELETE', `/users/${id}`);
    }

    // === USER MANAGEMENT ===

    async advancedSearchUsers(filters = {}, page = 1, perPage = 20) {
        const cleanFilters = {};
        Object.keys(filters).forEach(key => {
            if (filters[key] !== '' && filters[key] !== null && filters[key] !== undefined) {
                cleanFilters[key] = filters[key];
            }
        });

        const queryParams = new URLSearchParams({
            page: page,
            per_page: perPage,
            ...cleanFilters
        });
        return this.request('GET', `/users/advanced-search?${queryParams.toString()}`);
    }

    async batchCreateUsers(users) {
        return this.request('POST', '/users/batch-create', users);
    }

    async batchUpdateUsers(userIds, updateData) {
        return this.request('PATCH', '/users/batch-update', {
            user_ids: userIds,
            update_data: updateData
        });
    }

    async batchDeleteUsers(userIds, permanent = false) {
        const queryParams = new URLSearchParams();
        userIds.forEach(id => queryParams.append('user_ids', id));
        queryParams.append('permanent', permanent);
        return this.request('DELETE', `/users/batch-delete?${queryParams.toString()}`);
    }

    async exportUsers(filters = {}, format = 'csv') {
        const endpoint = `/users/export?format=${encodeURIComponent(format)}`;
        const config = {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify(filters || {})
        };

        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
            if (!response.ok) {
                let detail = 'Export failed';
                try {
                    const errorBody = await response.json();
                    detail = errorBody.detail || errorBody.message || detail;
                } catch (_) {}
                throw new Error(detail);
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `users_export_${new Date().toISOString().slice(0, 10)}.${format}`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            return { success: true };
        } catch (error) {
            console.error('Export error:', error);
            throw error;
        }
    }

    async getStudentClasses() {
        const result = await this.request('GET', '/users/student-classes');
        return result.classes || [];
    }

    async getStudentsByClass(studentClass = null) {
        const url = studentClass ? `/users/students-by-class?student_class=${encodeURIComponent(studentClass)}` : '/users/students-by-class';
        return this.request('GET', url);
    }

    // Exams endpoints
    async getExams(publishedOnly = false) {
        const response = await this.request('GET', `/exams?published_only=${publishedOnly}&limit=10000`);
        return response.exams || response;
    }

    async getExam(id) {
        return this.request('GET', `/exams/${id}`);
    }

    async createExam(examData) {
        return this.request('POST', '/exams', examData);
    }

    async updateExam(id, examData) {
        return this.request('PUT', `/exams/${id}`, examData);
    }

    async deleteExam(id) {
        return this.request('DELETE', `/exams/${id}`);
    }

    async publishExam(id, data = null) {
        return this.request('PATCH', `/exams/${id}/publish`, data);
    }

    async unpublishExam(id) {
        return this.request('PATCH', `/exams/${id}/publish`);
    }

    async createExamFromTemplate(templateId, startTime, endTime) {
        return this.request('POST', '/exams/from-template', {
            template_id: templateId,
            start_time: startTime,
            end_time: endTime
        });
    }

    async duplicateExam(examId, includeQuestions = true) {
        return this.request('POST', `/exams/${examId}/duplicate?include_questions=${includeQuestions}`);
    }

    async getExamAnalytics(examId) {
        return this.request('GET', `/exams/${examId}/analytics`);
    }

    async previewExam(examId, simulateStudentShuffle = false) {
        const query = simulateStudentShuffle ? '?simulate_student_shuffle=true' : '';
        return this.request('GET', `/exams/${examId}/preview${query}`);
    }


    // Questions endpoints
    async getQuestions(examId) {
        return this.request('GET', `/questions/${examId}/all`);
    }

    async createQuestion(questionData) {
        return this.request('POST', `/questions/${questionData.exam_id}`, questionData);
    }

    async updateQuestion(id, questionData) {
        return this.request('PUT', `/questions/${id}`, questionData);
    }

    async deleteQuestion(id) {
        return this.request('DELETE', `/questions/${id}`);
    }

    async uploadImage(file) {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_BASE_URL}/upload/image`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${this.token}` },
            body: formData
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Upload failed');
        }
        return response.json();
    }

    // === SUBJECTS ===
    async getSubjects() {
        return this.request('GET', '/subjects');
    }

    async createSubject(data) {
        return this.request('POST', '/subjects', data);
    }

    // === QUESTION BANK ===
    async getCategories() {
        return this.request('GET', '/questions/categories');
    }

    async createCategory(data) {
        return this.request('POST', '/questions/categories', data);
    }

    async getTags() {
        return this.request('GET', '/questions/tags');
    }

    async createTag(data) {
        return this.request('POST', '/questions/tags', data);
    }

    async searchQuestions(filters) {
        return this.request('POST', '/questions/search', filters);
    }

    async bulkUploadQuestions(examId, formData) {
        return fetch(`${API_BASE_URL}/questions/${examId}/bulk-upload`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${this.token}` },
            body: formData
        }).then(res => res.json());
    }

    async exportQuestions(examId, format = 'csv') {
        const response = await fetch(`${API_BASE_URL}/questions/${examId}/export?format=${format}`, {
            method: 'GET',
            headers: { 'Authorization': `Bearer ${this.token}` }
        });

        if (!response.ok) throw new Error('Export failed');
        return response.blob();
    }

    // Exam session endpoints
    async startExam(examId) {
        return this.request('POST', `/exams/${examId}/start`);
    }

    /**
     * Submit answer with strict type casting
     * IMPORTANT: This method auto-casts types to match backend Pydantic schema
     */
    async submitAnswer(sessionId, questionId, answerData) {
        // Normalize payload to match Pydantic AnswerSubmit schema
        const payload = {
            session_id: parseInt(sessionId) || 0,
            question_id: parseInt(questionId) || 0,
            ...this.normalizeAnswerPayload(answerData)
        };

        apiDebug('📤 Submitting answer:', payload);
        return this.request('POST', '/exams/submit-answer', payload);
    }

    /**
     * Normalize answer payload for Pydantic validation
     * Converts loose JS types to strict Python types
     */
    normalizeAnswerPayload(answerData) {
        const normalized = {};

        // Single selection (selected_option_id)
        if (answerData.selected_option_id !== undefined && answerData.selected_option_id !== null) {
            normalized.selected_option_id = parseInt(answerData.selected_option_id) || null;
        }

        // Multiple selections (selected_option_ids)
        if (answerData.selected_option_ids !== undefined && answerData.selected_option_ids !== null) {
            if (Array.isArray(answerData.selected_option_ids)) {
                normalized.selected_option_ids = answerData.selected_option_ids.map(id => parseInt(id)).filter(id => !isNaN(id));
            } else {
                normalized.selected_option_ids = [];
            }
        }

        // Matching pairs (matching_pairs)
        if (answerData.matching_pairs !== undefined && answerData.matching_pairs !== null) {
            if (typeof answerData.matching_pairs === 'object' && !Array.isArray(answerData.matching_pairs)) {
                // Convert all values to integers
                normalized.matching_pairs = {};
                Object.keys(answerData.matching_pairs).forEach(key => {
                    normalized.matching_pairs[key] = parseInt(answerData.matching_pairs[key]) || 0;
                });
            } else {
                normalized.matching_pairs = {};
            }
        }

        // Statement answers for PGK Table Validation (statement_answers)
        if (answerData.statement_answers !== undefined && answerData.statement_answers !== null) {
            if (typeof answerData.statement_answers === 'object' && !Array.isArray(answerData.statement_answers)) {
                // Keep boolean values as-is, convert keys to strings
                normalized.statement_answers = {};
                const parseBool = (v) => {
                    if (typeof v === 'boolean') return v;
                    if (typeof v === 'number') return v !== 0;
                    if (typeof v === 'string') {
                        const s = v.trim().toLowerCase();
                        if (['true', '1', 'yes', 'y', 'benar'].includes(s)) return true;
                        if (['false', '0', 'no', 'n', 'salah'].includes(s)) return false;
                    }
                    return false;
                };
                Object.keys(answerData.statement_answers).forEach(key => {
                    const value = answerData.statement_answers[key];
                    // Ensure boolean value (true/false) without Boolean("false") pitfall
                    normalized.statement_answers[String(key)] = parseBool(value);
                });
            } else {
                normalized.statement_answers = {};
            }
        }

        // Text answer (answer_text)
        if (answerData.answer_text !== undefined && answerData.answer_text !== null) {
            normalized.answer_text = String(answerData.answer_text);
        }

        // Metadata
        if (answerData.answer_metadata) {
            normalized.answer_metadata = answerData.answer_metadata;
        }

        return normalized;
    }

    async autoSave(sessionId, answers) {
        return this.request('POST', '/exams/auto-save', {
            session_id: parseInt(sessionId) || 0,
            answers: answers,
            timestamp: new Date().toISOString()  // Required by AutoSaveRequest schema
        });
    }

    async submitExam(sessionId) {
        return this.request('POST', '/exams/submit', { session_id: sessionId });
    }

    async joinExam(token) {
        return this.request('POST', '/exams/join', { token });
    }

    async regenerateToken(examId) {
        return this.request('POST', `/exams/${examId}/regenerate-token`);
    }

    // Results
    async getExamResults(examId, includeBreakdown = false) {
        const query = new URLSearchParams({
            include_breakdown: includeBreakdown ? 'true' : 'false'
        });
        return this.request('GET', `/exams/${examId}/results?${query.toString()}`);
    }

    async getExamParticipationSummary(examId) {
        return this.request('GET', `/exams/${examId}/participation-summary`);
    }

    async getSessionAnswerReview(examId, sessionId) {
        return this.request('GET', `/exams/${examId}/sessions/${sessionId}/review`);
    }

    async getExamsWithResults() {
        return this.request('GET', '/exams/results/all');
    }

    async getMyResults() {
        return this.request('GET', '/exams/my-results');
    }

    async getDashboardStats() {
        return this.request('GET', '/stats/dashboard');
    }

    // === GRADING ===
