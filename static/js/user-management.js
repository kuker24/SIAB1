/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/user-management/modules/*.js
 * Use scripts/build_user_management_bundle.sh after editing modules.
 */

/* ===== Module: 00-user-management-core.js ===== */

/**
 * User Management Module
 * Handles advanced search, filtering, batch operations, and export.
 */

class UserManagement {
    constructor() {
        this.currentPage = 1;
        this.perPage = 20;
        this.filters = {
            role: '',
            student_class: '',
            is_active: '',
            search_query: ''
        };
        this.selectedUsers = new Set();

        this.init();
    }

    init() {
        this.cacheDOM();
        this.bindEvents();
        this.loadUsers(); // Initial load
    }

    cacheDOM() {
        this.tableBody = document.getElementById('users-table-body');
        this.paginationContainer = document.getElementById('pagination-container');
        this.selectAllCheckbox = document.getElementById('select-all-users');
        this.totalCountSpan = document.getElementById('total-users-count');

        // Filter inputs
        this.roleFilter = document.getElementById('filter-role');
        this.classFilter = document.getElementById('filter-class');
        this.statusFilter = document.getElementById('filter-status');
        this.searchInput = document.getElementById('search-users');

        // Action buttons
        this.exportBtn = document.getElementById('btn-export-csv');
        this.batchDeleteBtn = document.getElementById('btn-batch-delete');
        this.refreshBtn = document.getElementById('btn-refresh');
    }

    bindEvents() {
        // Filters
        this.roleFilter?.addEventListener('change', (e) => this.handleFilterChange('role', e.target.value));
        this.classFilter?.addEventListener('change', (e) => this.handleFilterChange('student_class', e.target.value));
        this.statusFilter?.addEventListener('change', (e) => this.handleFilterChange('is_active', e.target.value));

        // Search with debounce
        let timeout;
        this.searchInput?.addEventListener('input', (e) => {
            clearTimeout(timeout);
            timeout = setTimeout(() => this.handleFilterChange('search_query', e.target.value), 500);
        });

        // Pagination
        this.paginationContainer?.addEventListener('click', (e) => {
            if (e.target.matches('.page-link')) {
                e.preventDefault();
                const page = parseInt(e.target.dataset.page);
                if (page && page !== this.currentPage) {
                    this.currentPage = page;
                    this.loadUsers();
                }
            }
        });

        // Selection
        this.selectAllCheckbox?.addEventListener('change', (e) => this.toggleSelectAll(e.target.checked));
        this.tableBody?.addEventListener('change', (e) => {
            if (e.target.classList.contains('user-checkbox')) {
                this.toggleUserSelection(parseInt(e.target.value), e.target.checked);
            }
        });

        // Actions
        this.exportBtn?.addEventListener('click', () => this.exportUsers());
        this.batchDeleteBtn?.addEventListener('click', () => this.confirmBatchDelete());
        this.refreshBtn?.addEventListener('click', () => this.loadUsers());
    }

    handleFilterChange(key, value) {
        this.filters[key] = value;
        this.currentPage = 1; // Reset to first page on filter change
        this.loadUsers();
    }

    async loadUsers() {
        try {
            this.showLoading();
            const response = await api.advancedSearchUsers(this.filters, this.currentPage, this.perPage);

            this.renderTable(response.users);
            this.renderPagination(response.total, response.page, response.per_page, response.total_pages);

            if (this.totalCountSpan) this.totalCountSpan.textContent = response.total;

            // Reset selection on page load? Or keep it? Usually reset is safer across pages unless we track carefully.
            this.selectedUsers.clear();
            if (this.selectAllCheckbox) this.selectAllCheckbox.checked = false;
            this.updateBatchActionsState();

        } catch (error) {
            console.error('Failed to load users:', error);
            this.showError('Gagal memuat data pengguna');
        } finally {
            this.hideLoading();
        }
    }

    renderTable(users) {
        if (!users.length) {
            this.tableBody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">Tidak ada data pengguna</td></tr>';
            return;
        }

        this.tableBody.innerHTML = users.map(user => {
            const fullName = user.full_name || user.username || 'Unknown';
            const initial = fullName.charAt(0).toUpperCase();
            const username = user.username || '-';
            const role = user.role || '-';
            const studentClass = user.student_class || '-';
            const isActive = user.is_active !== false;
            const createdAt = user.created_at ? new Date(user.created_at).toLocaleDateString('id-ID') : '-';

            return `
            <tr>
                <td class="ps-3">
                    <div class="form-check">
                        <input class="form-check-input user-checkbox" type="checkbox" value="${user.id}">
                    </div>
                </td>
                <td>
                    <div class="d-flex align-items-center">
                        <div class="avatar-circle bg-primary text-white me-2" style="width:36px;height:36px;display:flex;align-items:center;justify-content:center;border-radius:50%;font-weight:600;">
                            ${initial}
                        </div>
                        <div>
                            <div class="fw-bold" style="color: #f8fafc;">${fullName}</div>
                            <small style="color: #94a3b8;">${username}</small>
                        </div>
                    </div>
                </td>
                <td style="color: #e2e8f0;">${role}</td>
                <td style="color: #e2e8f0;">${studentClass}</td>
                <td>
                    <span class="badge ${isActive ? 'bg-success' : 'bg-danger'}">
                        ${isActive ? 'Aktif' : 'Non-Aktif'}
                    </span>
                </td>
                <td style="color: #e2e8f0;">${createdAt}</td>
                <td>
                    <div style="display: flex; gap: 0.5rem; align-items: center; justify-content: center;">
                        <button class="action-btn action-btn-edit" onclick="editUser(${user.id})">
                            <i class="fas fa-pen"></i>
                        </button>
                        <button class="action-btn action-btn-delete" onclick="deleteUser(${user.id})">
                            <i class="fas fa-trash-alt"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
        }).join('');
    }

    renderPagination(total, currentPage, perPage, totalPages) {
        if (totalPages <= 1) {
            this.paginationContainer.innerHTML = '';
            return;
        }

        let html = '<ul class="pagination pagination-sm mb-0">';

        // Prev
        html += `<li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" data-page="${currentPage - 1}">&laquo;</a>
        </li>`;

        // Pages (simple implementation, improved later for large numbers)
        for (let i = 1; i <= totalPages; i++) {
            // Show first, last, current, and adjacent
            if (i === 1 || i === totalPages || (i >= currentPage - 1 && i <= currentPage + 1)) {
                html += `<li class="page-item ${i === currentPage ? 'active' : ''}">
                    <a class="page-link" href="#" data-page="${i}">${i}</a>
                </li>`;
            } else if (i === currentPage - 2 || i === currentPage + 2) {
                html += '<li class="page-item disabled"><span class="page-link">...</span></li>';
            }
        }

        // Next
        html += `<li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
            <a class="page-link" href="#" data-page="${currentPage + 1}">&raquo;</a>
        </li>`;

        html += '</ul>';
        this.paginationContainer.innerHTML = html;
    }

    toggleSelectAll(checked) {
        const checkboxes = this.tableBody.querySelectorAll('.user-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = checked;
            this.toggleUserSelection(parseInt(cb.value), checked);
        });
    }

    toggleUserSelection(userId, isSelected) {
        if (isSelected) {
            this.selectedUsers.add(userId);
        } else {
            this.selectedUsers.delete(userId);
        }
        this.updateBatchActionsState();
    }

    updateBatchActionsState() {
        const count = this.selectedUsers.size;
        if (this.batchDeleteBtn) {
            this.batchDeleteBtn.disabled = count === 0;
            this.batchDeleteBtn.innerHTML = `<i class="fas fa-trash me-1"></i> Hapus terpilih (${count})`;
        }
    }

    async exportUsers() {
        try {
            this.exportBtn.disabled = true;
            this.exportBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Exporting...';
            await api.exportUsers(this.filters);
        } catch (error) {
            showError('Export failed: ' + error.message);
        } finally {
            this.exportBtn.disabled = false;
            this.exportBtn.innerHTML = '<i class="fas fa-file-export me-1"></i> Export CSV';
        }
    }

    async confirmBatchDelete() {
        const confirmed = await showConfirm(
            `Yakin ingin menghapus ${this.selectedUsers.size} pengguna? Tindakan ini tidak dapat dibatalkan.`,
            {
                title: 'Hapus Pengguna',
                type: 'danger',
                confirmText: 'Ya, Hapus',
                cancelText: 'Batal'
            }
        );
        if (!confirmed) return;

        try {
            await api.batchDeleteUsers(Array.from(this.selectedUsers), true);
            this.loadUsers();
            showSuccess('Pengguna berhasil dihapus');
        } catch (error) {
            showError('Gagal menghapus pengguna: ' + error.message);
        }
    }

    showLoading() {
        this.tableBody.innerHTML = '<tr><td colspan="7" class="text-center py-4"><i class="fas fa-spinner fa-spin fa-2x text-primary"></i></td></tr>';
    }

    hideLoading() {
        // Handled by render
    }

    showError(msg) {
        this.tableBody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-danger"><i class="fas fa-exclamation-triangle me-2"></i>${msg}</td></tr>`;
    }
}


/* ===== Module: 10-user-management-bootstrap.js ===== */

// Initializer
document.addEventListener('DOMContentLoaded', () => {
    window.userManagement = new UserManagement();
});
