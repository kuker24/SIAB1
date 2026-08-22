# AI Review Prompt - Ujian Online

Tujuan review: audit perubahan source code pada branch ini sebelum digabung ke produksi.

## Fokus utama
1. Keamanan penyimpanan/render soal:
   - `app/core/sanitization.py`
   - `scripts/fix_question_quote_entities.py`
   - `static/js/exam-builder.js`
   - `static/js/exam-builder/modules/*`
   - `templates/admin/exam-builder.html`
   - tests terkait quote escaping.
2. Restart aman antar sesi dan host-controlled restart:
   - `app/api/monitoring.py`
   - `app/api/monitoring_restart.py`
   - `app/core/restart_safe.py`
   - `app/tasks/scheduler.py`
   - `scripts/host_full_restart_worker.py`
   - `scripts/install_host_full_restart_systemd.sh`
   - tests terkait restart.
3. Middleware, monitoring, Redis/cache, Celery scheduler, dan pengaruhnya pada ujian aktif.
4. Frontend admin/student: XSS, unsafe HTML, token exposure, stale cache, and race conditions.
5. Docker/production config: least privilege, no secret hardcoding, safe healthchecks, and rollback risk.

## Batasan review
- Jangan menganggap credential nyata tersedia di repo. Semua secret harus berasal dari environment variables.
- Jangan menambahkan data siswa, soal asli, backup database, certificate/private key, atau file upload produksi.
- Jika menemukan file yang seharusnya tidak ada di Git, rekomendasikan penghapusan dan update `.gitignore`.

## Checklist yang diminta
- Temukan bug P0/P1 yang bisa memblokir ujian atau mengekspos data.
- Temukan hardcoded secret/token/password/private key.
- Validasi flow publish, start exam, submit answer, session recovery, restart-safe guard.
- Usulkan patch kecil dan regression test untuk setiap temuan penting.
