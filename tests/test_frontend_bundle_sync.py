from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path('.')
REGISTRY_FILE = ROOT / 'scripts/frontend_bundle_registry.csv'
EXAM_MODULE_ORDER = (
    'core.js',
    'bridge.js',
    'autosave.js',
    'security.js',
    'reconnect.js',
    'timer.js',
    'navigation.js',
)


def _render_bundle(module_dir: Path, source_hint: str, script_hint: str) -> str:
    header = (
        '/**\n'
        ' * AUTO-GENERATED FILE.\n'
        f' * Source modules: {source_hint}\n'
        f' * Use {script_hint} after editing modules.\n'
        ' */\n\n'
    )

    parts = [header]
    modules = sorted(module_dir.glob('*.js'))
    if source_hint == 'static/js/exam/*.js':
        modules = [module_dir / name for name in EXAM_MODULE_ORDER]

    for module in modules:
        parts.append(f'/* ===== Module: {module.name} ===== */\n\n')
        parts.append(module.read_text(encoding='utf-8'))
        parts.append('\n')
    return ''.join(parts).rstrip('\n') + '\n'


def _load_bundle_registry() -> list[tuple[str, str, str]]:
    if not REGISTRY_FILE.exists():
        raise AssertionError(f'Bundle registry file not found: {REGISTRY_FILE}')

    entries: list[tuple[str, str, str]] = []
    for raw_line in REGISTRY_FILE.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue

        parts = [part.strip() for part in line.split('|')]
        if len(parts) != 3:
            raise AssertionError(f'Invalid registry line (expected 3 columns): {raw_line}')

        bundle_path, module_glob, build_script = parts
        if not module_glob.endswith('*.js'):
            raise AssertionError(f'Invalid module glob (must end with *.js): {module_glob}')

        entries.append((bundle_path, module_glob, build_script))

    if not entries:
        raise AssertionError(f'No bundle entries found in registry: {REGISTRY_FILE}')
    return entries


_BUNDLE_CASES = _load_bundle_registry()


@pytest.mark.parametrize(
    'bundle_path,module_glob,build_script',
    _BUNDLE_CASES,
    ids=[bundle_path for bundle_path, _, _ in _BUNDLE_CASES],
)
def test_bundle_is_synced_with_modules(
    bundle_path: str,
    module_glob: str,
    build_script: str,
) -> None:
    bundle_file = ROOT / bundle_path
    module_dir = ROOT / module_glob[: -len('*.js')]

    assert bundle_file.is_file(), f'Bundle file not found: {bundle_file}'
    assert module_dir.is_dir(), f'Module directory not found: {module_dir}'

    expected = _render_bundle(module_dir, module_glob, build_script)
    actual = bundle_file.read_text(encoding='utf-8')
    assert actual == expected
