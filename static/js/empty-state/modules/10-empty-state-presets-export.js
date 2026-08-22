// Pre-configured empty states
const EmptyStates = {
    noExams: (container, action) => new EmptyState({
        container,
        icon: 'fas fa-file-alt',
        title: 'Belum Ada Ujian',
        description: 'Klik tombol di bawah untuk membuat ujian baru',
        action: action || null,
        variant: 'default'
    }),

    noStudents: (container, action) => new EmptyState({
        container,
        icon: 'fas fa-users',
        title: 'Belum Ada Siswa',
        description: 'Belum ada siswa yang terdaftar di sistem',
        action: action || null,
        variant: 'default'
    }),

    noResults: (container) => new EmptyState({
        container,
        icon: 'fas fa-chart-bar',
        title: 'Belum Ada Hasil',
        description: 'Hasil ujian akan muncul setelah siswa mengumpulkan jawaban',
        variant: 'default'
    }),

    noQuestions: (container, action) => new EmptyState({
        container,
        icon: 'fas fa-question-circle',
        title: 'Belum Ada Soal',
        description: 'Tambahkan soal untuk ujian ini',
        action: action || null,
        variant: 'warning'
    }),

    error: (container, message) => new EmptyState({
        container,
        icon: 'fas fa-exclamation-triangle',
        title: 'Terjadi Kesalahan',
        description: message || 'Silakan coba lagi nanti',
        variant: 'error'
    }),

    notFound: (container) => new EmptyState({
        container,
        icon: 'fas fa-search',
        title: 'Tidak Ditemukan',
        description: 'Data yang Anda cari tidak ditemukan',
        variant: 'warning'
    }),

    success: (container, title, description) => new EmptyState({
        container,
        icon: 'fas fa-check-circle',
        title: title || 'Berhasil!',
        description: description || 'Operasi berhasil dilakukan',
        variant: 'success'
    })
};

// Export for modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { EmptyState, EmptyStates };
}
