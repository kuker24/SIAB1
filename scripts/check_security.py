#!/usr/bin/env python3
"""
Dependency Vulnerability Scanner
Checks for known security vulnerabilities in Python dependencies.
Run this regularly or add to CI/CD pipeline.
"""
import subprocess
import sys
import json
import shutil
import os
from datetime import datetime
from pathlib import Path

PIP_AUDIT_CHECK_TIMEOUT = 20
PIP_AUDIT_SCAN_TIMEOUT = 300
PIP_LIST_TIMEOUT = 45
DEFAULT_ACCEPTLIST_PATH = "security/vulnerability_acceptlist.json"
STRICT_TELNET_CLIENT_ENV = "SECURITY_FAIL_ON_TELNET_CLIENT"
SKIP_OUTDATED_ENV = "SECURITY_SKIP_OUTDATED_CHECK"
DEFAULT_REQUIREMENTS_PATH = "requirements.txt"


def _load_acceptlist(path: str) -> list[dict]:
    file_path = Path(path)
    if not file_path.exists():
        return []

    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"⚠️  Failed to parse security acceptlist ({file_path}): {exc}")
        return []

    entries = payload.get("accepted_vulnerabilities")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _is_accept_entry_active(entry: dict) -> bool:
    until_raw = str(entry.get("until", "")).strip()
    if not until_raw:
        return True

    try:
        until_date = datetime.strptime(until_raw, "%Y-%m-%d").date()
    except ValueError:
        return False
    return datetime.utcnow().date() <= until_date


def _match_accept_entry(entries: list[dict], package_name: str, vuln_id: str) -> dict | None:
    package_name = package_name.strip().lower()
    vuln_id = vuln_id.strip().lower()

    for entry in entries:
        entry_package = str(entry.get("package", "")).strip().lower()
        entry_vuln_id = str(entry.get("id", "")).strip().lower()
        if entry_package != package_name or entry_vuln_id != vuln_id:
            continue
        if not _is_accept_entry_active(entry):
            continue
        return entry
    return None


def _detect_os_name() -> str:
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return ""
    try:
        data = os_release.read_text(encoding="utf-8")
    except Exception:
        return ""
    for line in data.splitlines():
        if line.startswith("ID="):
            return line.split("=", 1)[1].strip().strip('"').lower()
    return ""


def _get_telnet_remove_hint(telnet_path: str) -> str:
    distro_id = _detect_os_name()
    path = telnet_path.strip()
    if not path:
        return ""

    if shutil.which("pacman"):
        owner = _run_command(["pacman", "-Qo", path], timeout=10, text=True)
        if owner and owner.returncode == 0:
            parts = owner.stdout.strip().split()
            if len(parts) >= 5:
                package_name = parts[4]
                return f"sudo pacman -Rns {package_name}"
        return "sudo pacman -Rns inetutils"

    if shutil.which("dpkg"):
        owner = _run_command(["dpkg", "-S", path], timeout=10, text=True)
        if owner and owner.returncode == 0 and ":" in owner.stdout:
            package_name = owner.stdout.split(":", 1)[0].strip()
            if package_name:
                return f"sudo apt-get remove --purge -y {package_name}"
        if distro_id in {"ubuntu", "debian"}:
            return "sudo apt-get remove --purge -y inetutils-telnet telnet"
        return "sudo apt-get remove --purge -y telnet"

    if shutil.which("rpm"):
        owner = _run_command(["rpm", "-qf", path], timeout=10, text=True)
        if owner and owner.returncode == 0:
            package_name = owner.stdout.strip()
            if package_name:
                return f"sudo dnf remove -y {package_name}"
        return "sudo dnf remove -y telnet"

    return ""


def _is_truthy_env(env_name: str) -> bool:
    raw_value = os.getenv(env_name, "").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _normalize_package_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _parse_requirement_name(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    # Remove inline comments and environment markers before parsing package token.
    stripped = stripped.split("#", 1)[0].split(";", 1)[0].strip()
    if not stripped:
        return None

    for sep in ("==", ">=", "<=", "~=", "!=", ">", "<"):
        if sep in stripped:
            stripped = stripped.split(sep, 1)[0].strip()
            break

    if "[" in stripped:
        stripped = stripped.split("[", 1)[0].strip()

    if not stripped:
        return None
    return _normalize_package_name(stripped)


def _load_managed_requirements(path: str) -> set[str]:
    file_path = Path(path)
    if not file_path.exists():
        return set()

    managed_names: set[str] = set()
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return set()

    for line in lines:
        package_name = _parse_requirement_name(line)
        if package_name:
            managed_names.add(package_name)
    return managed_names


def _run_command(cmd, timeout, text=True):
    """Run subprocess command with timeout protection."""
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=text,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        print(f"⚠️  Command not found, skipping: {' '.join(cmd)}")
        return None
    except subprocess.TimeoutExpired:
        print(f"⚠️  Command timeout after {timeout}s: {' '.join(cmd)}")
        return None


def check_dependencies():
    """
    Check for vulnerabilities using pip-audit tool.
    Install with: pip install pip-audit
    """
    print("=" * 60)
    print("🔍 Dependency Vulnerability Scanner")
    print("=" * 60)
    print(f"Scan Time: {datetime.now().isoformat()}\n")
    acceptlist_path = os.getenv("SECURITY_ACCEPTLIST_FILE", DEFAULT_ACCEPTLIST_PATH).strip()
    accept_entries = _load_acceptlist(acceptlist_path)
    
    try:
        # Check if pip-audit is installed
        result = _run_command(
            [sys.executable, "-m", "pip", "show", "pip-audit"],
            timeout=PIP_AUDIT_CHECK_TIMEOUT,
            text=False,
        )

        if result is None:
            print("❌ pip-audit availability check timed out. Security status is unknown.")
            return 1

        if result.returncode != 0:
            print("❌ pip-audit is required for the security release gate.")
            print("   Install it in the active environment: pip install pip-audit")
            return 1
        
        # Run vulnerability scan
        print("Scanning dependencies for known vulnerabilities...\n")
        
        result = _run_command(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "-r",
                os.getenv("SECURITY_REQUIREMENTS_FILE", DEFAULT_REQUIREMENTS_PATH),
                "--desc",
                "--format",
                "json",
            ],
            timeout=PIP_AUDIT_SCAN_TIMEOUT,
            text=True,
        )

        if result is None:
            print("❌ Vulnerability scan timed out. Security status is unknown.")
            return 1

        try:
            vulnerabilities = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            print("⚠️  Error parsing vulnerability report")
            print(result.stdout)
            if result.stderr:
                print(result.stderr)
            return 1

        dependencies = vulnerabilities.get("dependencies", [])
        vulnerable_deps = [dep for dep in dependencies if dep.get("vulns")]

        actionable_findings = []
        accepted_findings = []
        for dep in vulnerable_deps:
            package_name = str(dep.get("name") or "unknown")
            package_version = str(dep.get("version") or "unknown")
            for issue in dep.get("vulns", []):
                vuln_id = str(issue.get("id") or "N/A")
                accept_entry = _match_accept_entry(accept_entries, package_name, vuln_id)
                finding = {
                    "package": package_name,
                    "version": package_version,
                    "issue": issue,
                    "accept": accept_entry,
                }
                if accept_entry is not None:
                    accepted_findings.append(finding)
                else:
                    actionable_findings.append(finding)

        if not actionable_findings and not accepted_findings:
            print("✅ SUCCESS: No known vulnerabilities found!")
            return 0

        if actionable_findings:
            actionable_packages = {(f["package"], f["version"]) for f in actionable_findings}
            print(f"🚨 FOUND {len(actionable_packages)} ACTIONABLE VULNERABLE PACKAGES:\n")
            for package_name, package_version in sorted(actionable_packages):
                print(f"📦 Package: {package_name} {package_version}")
                package_findings = [
                    finding for finding in actionable_findings
                    if finding["package"] == package_name and finding["version"] == package_version
                ]
                for finding in package_findings:
                    issue = finding["issue"]
                    fix_versions = issue.get("fix_versions") or []
                    suggested_fix = fix_versions[0] if fix_versions else "no patched version available"
                    print(f"   ⚠️  CVE: {issue.get('id', 'N/A')}")
                    print(f"   Description: {issue.get('description', 'No description')}")
                    print(f"   Fix: Upgrade to {suggested_fix}")
                    print()

            print("\n🔧 To fix, run:")
            print("   pip install --upgrade <package-name>")
            print("\nOr update requirements.txt and run:")
            print("   pip install -r requirements.txt --upgrade")

        if accepted_findings:
            accepted_packages = {(f["package"], f["version"]) for f in accepted_findings}
            print(f"\n✅ ACCEPTED RISKS ({len(accepted_packages)} package):")
            print(f"   Policy file: {acceptlist_path}")
            for package_name, package_version in sorted(accepted_packages):
                print(f"📦 Package: {package_name} {package_version}")
                package_findings = [
                    finding for finding in accepted_findings
                    if finding["package"] == package_name and finding["version"] == package_version
                ]
                for finding in package_findings:
                    issue = finding["issue"]
                    accept = finding["accept"] or {}
                    mitigation = str(accept.get("mitigation") or "No mitigation note")
                    reason = str(accept.get("reason") or "No reason note")
                    until = str(accept.get("until") or "no-expiry")
                    print(f"   ℹ️  CVE: {issue.get('id', 'N/A')} (accepted until {until})")
                    print(f"      Reason: {reason}")
                    print(f"      Mitigation: {mitigation}")

        return 1 if actionable_findings else 0
    
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running scan: {e}")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1


def check_outdated_packages():
    """Check for outdated packages."""
    print("\n" + "=" * 60)
    print("📦 Checking for outdated packages...")
    print("=" * 60 + "\n")
    
    try:
        result = _run_command(
            [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"],
            timeout=PIP_LIST_TIMEOUT,
            text=True,
        )

        if result is None:
            print("⚠️  Outdated package check timed out")
            return 0

        if result.returncode != 0:
            print("⚠️  Could not query outdated packages")
            if result.stderr:
                print(result.stderr.strip())
            return 0
        
        outdated = json.loads(result.stdout)
        
        if not outdated:
            print("✅ All packages are up to date!")
            return 0
        else:
            requirements_path = os.getenv("SECURITY_REQUIREMENTS_FILE", DEFAULT_REQUIREMENTS_PATH).strip()
            managed_names = _load_managed_requirements(requirements_path)

            managed_outdated = []
            transitive_outdated = []
            for pkg in outdated:
                name = _normalize_package_name(pkg.get("name", ""))
                if managed_names and name in managed_names:
                    managed_outdated.append(pkg)
                else:
                    transitive_outdated.append(pkg)

            print(f"📊 Found {len(outdated)} outdated packages:\n")

            if managed_outdated:
                print(f"   Managed requirements ({len(managed_outdated)}):")
                for pkg in managed_outdated:
                    print(f"   - {pkg['name']}: {pkg['version']} → {pkg['latest_version']}")

            if transitive_outdated:
                print(f"\n   Transitive/indirect ({len(transitive_outdated)}):")
                for pkg in transitive_outdated:
                    print(f"   - {pkg['name']}: {pkg['version']} → {pkg['latest_version']}")
            
            print("\n💡 TIP: Review changelogs before upgrading critical packages")
            return 0
    except Exception as e:
        print(f"⚠️  Could not check outdated packages: {e}")
        return 0


def check_system_vulnerabilities():
    """Check for system-level vulnerabilities (like Telnet)."""
    print("\n" + "=" * 60)
    print("🛡️  Checking System Vulnerabilities...")
    print("=" * 60 + "\n")
    
    issues_found = 0
    
    # 1. Check for Telnet exposure (CVE-2026-24061)
    telnet_path = shutil.which("telnet")
    inetutils_path = shutil.which("inetutils-telnetd")

    telnet_port_open = False
    ss_result = _run_command(["ss", "-ltn"], timeout=10, text=True)
    if ss_result and ss_result.returncode == 0:
        telnet_port_open = ":23 " in ss_result.stdout or ":23\n" in ss_result.stdout

    if inetutils_path or telnet_port_open:
        print("🚨 CRITICAL: Telnet service exposure detected!")
        print(f"   - telnetd path: {inetutils_path or 'not found'}")
        print(f"   - port 23 listening: {telnet_port_open}")
        print("   - Risk: High (possible remote abuse on legacy Telnet service)")
        print("   - Action: Disable/remove telnet daemon immediately.")
        issues_found += 1
    elif telnet_path:
        print("⚠️  WARNING: Telnet client binary found (not daemon/listening).")
        print(f"   - client path: {telnet_path}")
        print("   - Risk: Low operational risk; hardening recommendation only.")
        remove_hint = _get_telnet_remove_hint(telnet_path)
        if remove_hint:
            print(f"   - Action: Optional remove package if not needed -> `{remove_hint}`")
        else:
            print("   - Action: Optional remove package if not needed.")
        if _is_truthy_env(STRICT_TELNET_CLIENT_ENV):
            print(
                f"   - STRICT MODE: env `{STRICT_TELNET_CLIENT_ENV}=1` aktif, "
                "telnet client dianggap issue blocking."
            )
            issues_found += 1
    else:
        print("✅ Telnet exposure check passed (no daemon and no listener on port 23)")
        
    return issues_found


if __name__ == "__main__":
    print("\n🛡️  SECURITY DEPENDENCY AUDIT\n")
    
    # Check system vulnerabilities
    sys_vuln_status = check_system_vulnerabilities()
    
    # Check vulnerabilities
    vuln_status = check_dependencies()
    
    # Check outdated (optional for deterministic/offline gate runs)
    if _is_truthy_env(SKIP_OUTDATED_ENV):
        print("\n" + "=" * 60)
        print("📦 Checking for outdated packages...")
        print("=" * 60 + "\n")
        print(f"⏭️  Skipped by env `{SKIP_OUTDATED_ENV}=1`")
        outdated_status = 0
    else:
        outdated_status = check_outdated_packages()
    
    print("\n" + "=" * 60)
    if vuln_status == 0 and sys_vuln_status == 0:
        print("✅ SECURITY CHECK PASSED")
    else:
        print("🚨 ACTION REQUIRED: Fix vulnerabilities above")
    print("=" * 60 + "\n")
    
    sys.exit(vuln_status + sys_vuln_status)
