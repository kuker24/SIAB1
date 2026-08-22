#!/usr/bin/env python3
"""
Generate a lightweight markdown index for the `reports/` directory.

Purpose:
- Keep report artifacts discoverable without changing report data.
- Preserve historical benchmark/debug files for forensic analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
OUTPUT_FILE = REPORTS_DIR / "INDEX.md"


@dataclass(frozen=True)
class ReportEntry:
    name: str
    path: Path
    is_dir: bool
    mtime: datetime
    size_bytes: int
    category: str
    retention_class: str


def _size_of(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def _classify_entry(name: str) -> tuple[str, str]:
    lower = name.lower()

    if lower.endswith(".certification.json"):
        return ("super-load-certification", "KEEP_CRITICAL")
    if lower.startswith("load_2000_super"):
        return ("super-load", "KEEP_LONG")
    if lower.startswith("load_1000") or lower.startswith("benchcap"):
        return ("benchmark-load", "KEEP_LONG")
    if lower.startswith("prod_e2e"):
        return ("e2e-snapshot", "KEEP_MEDIUM")
    if lower.startswith("vps_realtime"):
        return ("runtime-forensics", "KEEP_CRITICAL")
    if lower.startswith("adb_outage"):
        return ("incident-outage", "KEEP_CRITICAL")
    if lower.startswith("autonomous_full_test"):
        return ("autonomous-test", "KEEP_MEDIUM")
    if lower.startswith("deep_clean"):
        return ("maintenance", "KEEP_SHORT")

    return ("misc", "KEEP_MEDIUM")


def _iter_entries(base_dir: Path) -> Iterable[ReportEntry]:
    for item in sorted(base_dir.iterdir(), key=lambda p: p.name.lower()):
        if item.name.startswith(".") or item.name == "INDEX.md":
            continue
        stat = item.stat()
        category, retention_class = _classify_entry(item.name)
        yield ReportEntry(
            name=item.name,
            path=item,
            is_dir=item.is_dir(),
            mtime=datetime.fromtimestamp(stat.st_mtime),
            size_bytes=_size_of(item),
            category=category,
            retention_class=retention_class,
        )


def _human_size(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    unit = units[0]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024.0
    return f"{size:.2f} {unit}"


def build_markdown(entries: list[ReportEntry]) -> str:
    lines: list[str] = []
    retention_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}

    for entry in entries:
        retention_counts[entry.retention_class] = (
            retention_counts.get(entry.retention_class, 0) + 1
        )
        category_counts[entry.category] = category_counts.get(entry.category, 0) + 1

    lines.append("# Reports Index")
    lines.append("")
    lines.append(
        "Daftar artefak benchmark, load-test, dan investigasi di `reports/`, "
        "dilengkapi klasifikasi retensi."
    )
    lines.append("")
    lines.append(f"- Total entri: **{len(entries)}**")
    lines.append(
        f"- Dibuat ulang: **{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**"
    )
    lines.append("")
    lines.append("## Ringkasan Retensi")
    lines.append("")
    for key in sorted(retention_counts.keys()):
        lines.append(f"- `{key}`: {retention_counts[key]} entri")
    lines.append("")
    lines.append("## Ringkasan Kategori")
    lines.append("")
    for key in sorted(category_counts.keys()):
        lines.append(f"- `{key}`: {category_counts[key]} entri")
    lines.append("")
    lines.append("| Nama | Jenis | Kategori | Retensi | Ukuran | Terakhir Diubah |")
    lines.append("|---|---|---|---|---:|---|")

    for entry in sorted(entries, key=lambda e: e.mtime, reverse=True):
        kind = "folder" if entry.is_dir else "file"
        relative = entry.path.relative_to(REPORTS_DIR).as_posix()
        lines.append(
            f"| [{entry.name}]({relative}) | {kind} | {entry.category} | "
            f"{entry.retention_class} | {_human_size(entry.size_bytes)} | "
            f"{entry.mtime.strftime('%Y-%m-%d %H:%M:%S')} |"
        )

    lines.append("")
    lines.append("## Kebijakan")
    lines.append("")
    lines.append("- Tidak ada data laporan yang dihapus otomatis oleh script ini.")
    lines.append(
        "- Klasifikasi retensi digunakan untuk pengelolaan cerdas (prioritas simpan), "
        "bukan auto-delete."
    )
    lines.append("- `KEEP_CRITICAL`: artefak investigasi/sertifikasi prioritas tertinggi.")
    lines.append("- `KEEP_LONG`: benchmark kapasitas, simpan jangka panjang.")
    lines.append("- `KEEP_MEDIUM`: artefak validasi rutin, simpan menengah.")
    lines.append("- `KEEP_SHORT`: artefak maintenance, simpan pendek sesuai kebutuhan tim.")
    lines.append("")
    lines.append("## Regenerasi")
    lines.append("")
    lines.append("```bash")
    lines.append("python scripts/generate_reports_index.py")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not REPORTS_DIR.exists():
        raise SystemExit(f"reports directory not found: {REPORTS_DIR}")

    entries = list(_iter_entries(REPORTS_DIR))
    content = build_markdown(entries)
    OUTPUT_FILE.write_text(content, encoding="utf-8")
    print(f"Generated {OUTPUT_FILE} with {len(entries)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
