# Template Hasil Load Test Phase 4 — Direct Mode

Gunakan template ini hanya untuk local/staging. Jangan gunakan untuk production load test.

```text
Tanggal:
Environment: local/staging, bukan production
Commit:
Mode:
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
EXAM_PEAK_MODE=true/false
Peserta synthetic:
Durasi:
Endpoints tested:
submit-answer total:
submit-answer 2xx:
submit-answer 4xx:
submit-answer 429:
submit-answer 5xx:
client timeout/exception:
p50/p95/p99 jika tersedia:
final submit sample count:
final submit success:
DB/PgBouncer notes:
Redis notes:
Answer consistency check:
Conclusion:
GO/NO-GO Phase 5:
Follow-up:
```

## Checklist Pengisian

- Pastikan dataset synthetic, bukan data siswa real.
- Pastikan host bukan production.
- Pastikan direct safe-mode aktif.
- Pastikan queue/hybrid/runtime buffer tetap off.
- Pastikan dashboard hanya summary/aggregate.
- Jangan menjalankan heavy export saat test.
- Catat semua 5xx, 429, client timeout/status 0.
- Catat final submit sample secara terpisah dari answer autosave.
- Jika direct 300 gagal gate, jangan lanjut 600 sampai root cause jelas.
- Jika direct 600 repeated 5xx atau final-submit failure, Phase 5 tetap NO-GO.
