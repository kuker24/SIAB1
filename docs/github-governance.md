# GitHub governance

`main` is the reconciled source-of-truth. Production remains a file-based release.

## Main

- Pull request required. Direct push is blocked.
- Required check: `validate` from workflow `Production hardening checks`.
- The branch must be up to date with `main` before merge.
- Unresolved review conversations must be resolved.
- Force-push and deletion of `main` are blocked.
- Merge commits, squash, and rebase remain allowed. Prefer merge commits unless a PR needs a different method.
- Repository ruleset bypass actors: none. An admin can still change the ruleset in GitHub Settings.

## Stable tags

Format: `stable-*` (example: `stable-2026-08-28`).

- Create new stable tags from protected `main` after release gates pass.
- Do not delete or move existing `stable-*` tags.
- Production deploy still requires passing gates, a backup, and a delta/full manifest with source fingerprint.

## Runtime rollback

A production rollback does not rewrite Git history.

1. Swap only the affected student route back to FastAPI, or restore a prior deployment artifact.
2. Follow with a revert pull request on `main`.

Do not force-reset protected `main` as routine rollback.
