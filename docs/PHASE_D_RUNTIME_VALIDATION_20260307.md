# Phase D Runtime Validation Report

Tanggal: 2026-03-07
Lingkup: Validasi stabilitas runtime + regression guard untuk release vNext (offline package + answer journal + resume guard)

## Ringkasan Hasil
- Status: **PASS dengan catatan batas environment**
- Target eksternal (`https://man1rokanhulu.cloud`) merespons sehat.
- Validasi kode dan bundle lulus (Python compile, Flutter analyze/test, JS syntax check).
- `pytest` berhasil berjalan via environment virtual (`.venv`).

## Eksekusi dan Hasil

### 1) Synthetic Runtime Guard (external)
Perintah:
```bash
python3 scripts/synthetic_runtime_guard.py \
  --base-url https://man1rokanhulu.cloud \
  --samples 8 --sleep-ms 300 --timeout-sec 8 \
  --max-error-percent 5 --max-p95-ms 2500
```

Hasil penting:
- `/health` success rate: **100%** (8/8)
- p50 latency: **99.61 ms**
- p95 latency: **153.02 ms**
- max latency: **177.86 ms**
- Guard verdict: **PASS**

### 2) Critical HTTP Path Regression (external)
Perintah:
```bash
BASE_URL='https://man1rokanhulu.cloud' bash scripts/verify_critical_http_paths.sh
```

Hasil:
- Passed: **9**
- Failed: **0**
- Endpoint kritikal (`/health`, auth path, submit path existence, monitoring path) lolos regex status yang diharapkan.

### 3) Pytest Contract + Guard
Perintah:
```bash
.venv/bin/python -m pytest -q \
  tests/test_answer_journal_contract.py \
  tests/test_submit_hotpath_guard.py
```

Hasil:
- **20 passed** in 0.03s

### 4) Flutter Static + Unit Smoke
Perintah:
```bash
cd flutter_client_code
flutter analyze lib/pages/exam_page.dart lib/services/api_service.dart \
  lib/services/exam_resilience_service.dart lib/config.dart
flutter test --reporter compact
```

Hasil:
- Analyze: **No issues found**
- Test: **All tests passed**

### 5) Backend + JS Build/Parse Guard
Perintah:
```bash
python3 -m compileall app
python3 -m py_compile tools/apk_builder_gui.py
bash scripts/build_exam_system_bundle.sh
node --check static/js/exam-system.js
node --check static/sw.js
```

Hasil:
- Semua perintah lulus tanpa syntax error.

## Catatan Batas Environment
- Simulasi outage container-level (stop/start service) **tidak bisa dijalankan dari environment ini** karena Docker daemon tidak tersedia (`/var/run/docker.sock` tidak ada).
- Full E2E login/session dengan akun admin/guru/siswa live tidak dilakukan pada report ini (kredensial tidak disediakan di environment terminal saat eksekusi).

## Verdict
- Paket perubahan siap lanjut ke tahap rollout terbatas.
- Untuk validasi akhir Hari-H, jalankan tambahan:
  1. Outage simulation 5/10/30 menit pada host VPS (dengan docker/systemd aktif).
  2. Device-level restart APK saat sesi berjalan untuk verifikasi resume `< 5 detik`.
