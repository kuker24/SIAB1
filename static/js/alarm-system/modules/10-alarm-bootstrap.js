// Initialize on exam pages
document.addEventListener('DOMContentLoaded', () => {
    const examContainer = document.getElementById('exam-container');
    if (examContainer) {
        const sessionId = parseInt(examContainer.dataset.sessionId);
        const examId = parseInt(examContainer.dataset.examId);

        window.cheatAlarm = new CheatDetectionAlarm(sessionId, examId);
        return;
    }

    const savedSession = localStorage.getItem('active_exam_session');
    if (savedSession) {
        try {
            const sessionData = JSON.parse(savedSession);
            if (sessionData?.sessionId && sessionData?.examId) {
                window.cheatAlarm = new CheatDetectionAlarm(
                    parseInt(sessionData.sessionId, 10),
                    parseInt(sessionData.examId, 10)
                );
            }
        } catch (error) {
            console.warn('Failed to restore cheat alarm session:', error);
        }
    }
});
