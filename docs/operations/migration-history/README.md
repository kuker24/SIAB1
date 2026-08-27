# Production Migration Provenance

This directory records SQL artifacts found in the production application tree for
`live-control-20260826-3f8fc938a226`.

## Safety Contract

- Files under `archive/` are inert evidence, not executable migrations.
- The archived files use the `.sql.txt` suffix and live outside `app/migrations` so
  migration discovery cannot execute them.
- Three archived scripts have no matching effect in the current production schema.
- Committing an archived file never means that it should be applied.
- SIAB1 has no authoritative migration ledger. Filename order is not application order.
- Never execute an archive file against a database without a separately approved change.

## Canonical Status

| Production file | Provenance | Production DB evidence | Canonical treatment |
|---|---|---|---|
| `20260312_partition_exam_logs_and_hot_indexes.sql` | Never tracked in canonical or legacy Git objects | Absent; `exam_logs` remains a heap and all named indexes are absent | Archive as unapplied evidence |
| `20260313_exam_logs_partition_maintenance.sql` | Never tracked in canonical or legacy Git objects | Function and generated partitions are absent | Archive as unapplied evidence |
| `20260418_users_role_guruplus.sql` | Never tracked in canonical or legacy Git objects | Constraint effect is present, but the same effect is enforced by `app/database.py` | Archive as ambiguous historical evidence |
| `20260423_developer_role_and_seed_accounts.sql` | Production body was never tracked; sanitized replacement entered canonical Git at `0af42f40bf2224870bda38d402f6985ac4706148` | Referenced accounts are absent and no account uses the embedded hash | Do not archive the production body; keep the sanitized replacement |
| `create_materialized_views.sql` | Exact blob introduced in legacy commit `c40b2469792b6cbb395b7d307cac700ada8bc6f5` and copied into sanitized-root commit `2d853cbfd6a390c33d42ed2a9281ae2d8afec429` | Materialized views and their indexes are absent | Archive as unapplied evidence |

## Credential Hygiene

The production-only body of `20260423_developer_role_and_seed_accounts.sql`
contains one hardcoded bcrypt password hash reused by update/upsert statements. It
does not contain a plaintext password. The hash occurred in legacy Git history in
`docker/init.sql`, but does not occur in the canonical SIAB1 Git object database.

Read-only production verification found:

- no referenced migration account still present;
- no production account using the embedded hash;
- no active production account using the embedded hash.

The production body is intentionally not copied into this history. Its sanitized
replacement is `app/migrations/20260423_developer_role_and_seed_accounts.sql`.

## Runner Semantics

The repository has no Alembic configuration, SQL glob runner, or migration ledger.
`scripts/init_materialized_views.py` is an explicit manual command, while
`app/tasks/views_refresher.py` owns the current optional materialized-view DDL.
`app/database.py` owns the current users-role compatibility constraint.

The archive therefore documents provenance without expanding any executable
migration path.

## Control Identity

- Control ID: `siab1-control-20260827-app-3f8fc938a226-mig-08519407c207`
- Application tree: `3f8fc938a226dbb479461842539f5e83c1e4c77cbb781c2cd4050520be0d4640`
- Canonical migration set: `08519407c20727210f665d8b25556ba93eb5de2d4a549216b088b2049855d241`
- Schema fingerprint: `fe17317063614ce1875015bc8d1a2cc744904ab0269bcc24ab9bc3e7fe59961f`

Machine-readable copy: `CONTROL_MANIFEST.json`.

## Verification

Run the deterministic read-only schema fingerprint from an application environment:

```bash
python scripts/schema_fingerprint_readonly.py
```

The command opens a read-only transaction and prints only object counts and a SHA-256
fingerprint. It excludes table rows, credential hashes, PII, and unstable timestamps.
