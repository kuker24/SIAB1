// Global functions
let examScheduler;

function initExamScheduler(examId) {
    examScheduler = new ExamScheduler(examId);
    examScheduler.loadSchedules();
}

function openScheduleModal() {
    examScheduler.showScheduleModal();
}

function closeScheduleModal() {
    const modal = document.getElementById('schedule-modal');
    if (modal) modal.remove();
}
