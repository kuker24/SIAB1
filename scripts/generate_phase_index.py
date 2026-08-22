#!/usr/bin/env python3
"""
Generate docs/PHASE_INDEX.md from phase report files.

Goal:
- Keep phase documentation consolidated in one index.
- Preserve existing report files and changelog structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
OUTPUT_FILE = DOCS_DIR / "PHASE_INDEX.md"
PHASE_PATTERN = re.compile(r"^PHASE(\d+)_REPORT\.md$")


@dataclass(frozen=True)
class PhaseEntry:
    phase_number: int
    file_name: str
    path: Path
    modified: datetime
    title: str


def _read_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return path.stem.replace("_", " ")


def _collect_phase_entries() -> list[PhaseEntry]:
    entries: list[PhaseEntry] = []
    for candidate in DOCS_DIR.iterdir():
        if not candidate.is_file():
            continue
        match = PHASE_PATTERN.match(candidate.name)
        if not match:
            continue
        phase_number = int(match.group(1))
        stat = candidate.stat()
        entries.append(
            PhaseEntry(
                phase_number=phase_number,
                file_name=candidate.name,
                path=candidate,
                modified=datetime.fromtimestamp(stat.st_mtime),
                title=_read_title(candidate),
            )
        )
    return sorted(entries, key=lambda e: e.phase_number)


def _build_markdown(entries: list[PhaseEntry]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    lines.append("# Phase Reports Index")
    lines.append("")
    lines.append("Konsolidasi daftar phase report frontend/backend refactor.")
    lines.append("")
    lines.append(f"- Total phase report: **{len(entries)}**")
    lines.append(f"- Dibuat ulang: **{now}**")
    lines.append("")
    lines.append("| Phase | Judul | File | Last Modified |")
    lines.append("|---:|---|---|---|")

    for entry in entries:
        relative = entry.path.relative_to(DOCS_DIR).as_posix()
        lines.append(
            f"| {entry.phase_number} | {entry.title} | "
            f"[{entry.file_name}]({relative}) | "
            f"{entry.modified.strftime('%Y-%m-%d %H:%M:%S')} |"
        )

    lines.append("")
    lines.append("## Referensi")
    lines.append("")
    lines.append("- `docs/PHASE_CHANGELOG.md` sebagai ringkasan naratif lintas phase.")
    lines.append("- File `docs/PHASE*_REPORT.md` tetap dipertahankan untuk detail teknis.")
    lines.append("")
    lines.append("## Regenerasi")
    lines.append("")
    lines.append("```bash")
    lines.append("python scripts/generate_phase_index.py")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not DOCS_DIR.exists():
        raise SystemExit(f"docs directory not found: {DOCS_DIR}")

    entries = _collect_phase_entries()
    content = _build_markdown(entries)
    OUTPUT_FILE.write_text(content, encoding="utf-8")
    print(f"Generated {OUTPUT_FILE} with {len(entries)} phase entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
