// Global instance
let templateManager;

function initTemplateManager() {
    templateManager = new ExamTemplateManager();
    templateManager.loadTemplates();
}

function closeCreateExamModal() {
    const modal = document.getElementById('create-exam-modal');
    if (modal) modal.remove();
}
