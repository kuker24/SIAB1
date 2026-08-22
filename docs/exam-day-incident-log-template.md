# Exam-Day Incident Log Template

Gunakan template ini untuk mencatat incident saat ujian aktif. Jangan memasukkan password, token rahasia, jawaban siswa, screenshot data sensitif, atau data pribadi yang tidak perlu.

## Template Singkat

```text
Tanggal:
Jam mulai:
Jam selesai:
Ruang/kelas:
Jumlah peserta terdampak:
Fitur terdampak: login/start/autosave/final-submit/dashboard/cheating-monitoring
Gejala:
Endpoint jika diketahui:
Apakah peserta lain normal:
Status answer/final-submit:
Tindakan panitia:
Tindakan operator:
Keputusan: lanjut wave / tahan wave / emergency review
Approval jika ada:
Hasil akhir:
Follow-up setelah ujian:
```

## Template Lengkap

```text
Incident ID:
Severity: S0/S1/S2/S3/S4
Tanggal:
Jam mulai:
Jam selesai:
Ruang/kelas:
Jumlah peserta terdampak:
Total peserta ruang/gelombang:

Fitur terdampak:
- login / start / autosave / final-submit / dashboard / cheating-monitoring

Gejala:
Endpoint jika diketahui:
Pesan error yang terlihat:
Apakah peserta lain normal:
Status answer/final-submit:
Apakah final submit berisiko: ya/tidak/tidak diketahui
Apakah jawaban siswa berisiko: ya/tidak/tidak diketahui

Read-only indicator:
- API health:
- 4xx/5xx trend:
- DB pressure:
- Redis backlog:
- Nginx error trend:
- Dashboard summary:

Tindakan panitia:
Tindakan operator:
Tindakan backend reviewer read-only:

Keputusan:
- lanjut wave / tahan wave / kurangi dashboard / stop export / emergency review

Approval jika ada:
- Decision owner:
- Waktu approval:
- Scope approval:

Hasil akhir:
Dampak akhir:
Follow-up setelah ujian:
Owner follow-up:
```

## Severity Reference

- **S0 normal:** tidak ada gangguan berarti.
- **S1 minor isolated issue:** sedikit siswa terdampak, sistem umum normal.
- **S2 multiple students affected:** beberapa siswa terdampak, answer/final-submit sebagian besar normal.
- **S3 many 5xx/final-submit risk:** banyak error atau final submit mulai berisiko.
- **S4 critical outage/data safety risk:** outage kritis atau risiko keselamatan jawaban/data.

## Keputusan Operasional

- **Lanjut wave:** hanya jika sistem stabil atau issue isolated.
- **Tahan wave:** jika error meluas, 5xx naik, DB/API pressure, atau final-submit lambat.
- **Emergency review:** jika S3/S4, final-submit risk, data safety risk, atau outage.

## Larangan Saat Mencatat Incident

- Jangan mencatat password/token/secret.
- Jangan menyalin jawaban siswa.
- Jangan mengekspor report berat saat peak hanya untuk incident log.
- Jangan melakukan restart/deploy/migration/load test sebagai bagian dari logging.
- Jangan mengubah data siswa secara destruktif.
