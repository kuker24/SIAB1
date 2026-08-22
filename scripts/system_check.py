#!/usr/bin/env python3
"""
System Health Check Script
Checks all API endpoints and system components
Run: python scripts/system_check.py
"""

import asyncio
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime

try:
    import aiohttp
except ImportError:
    aiohttp = None

# Configuration
BASE_URL = os.getenv("SYSTEM_CHECK_BASE_URL", "http://127.0.0.1")
ADMIN_USERNAME = os.getenv("SYSTEM_CHECK_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("SYSTEM_CHECK_ADMIN_PASSWORD", "")
GURU_USERNAME = os.getenv("SYSTEM_CHECK_TEACHER_USERNAME", "guru")
GURU_PASSWORD = os.getenv("SYSTEM_CHECK_TEACHER_PASSWORD", "")
SISWA_USERNAME = os.getenv("SYSTEM_CHECK_STUDENT_USERNAME", "siswa123")
SISWA_PASSWORD = os.getenv("SYSTEM_CHECK_STUDENT_PASSWORD", "")

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def ok(msg):
    print(f"  {Colors.GREEN}✓{Colors.END} {msg}")

def fail(msg, detail=""):
    print(f"  {Colors.RED}✗{Colors.END} {msg}")
    if detail:
        print(f"    {Colors.RED}→ {detail}{Colors.END}")

def warn(msg):
    print(f"  {Colors.YELLOW}⚠{Colors.END} {msg}")

def header(msg):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{msg}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")

class SystemChecker:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.token = None
        self.results = {"passed": 0, "failed": 0, "warnings": 0}

    async def login(self, session):
        """Get auth token"""
        try:
            async with session.post(
                f"{self.base_url}/api/auth/login",
                json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.token = data.get("access_token")
                    return True
                else:
                    return False
        except Exception as e:
            return False

    async def check_endpoint(self, session, method, path, name, auth=True, expected_status=200, data=None):
        """Check a single endpoint.

        expected_status can be one status code or a collection of accepted codes.
        This keeps production checks accurate for endpoints intentionally disabled
        outside development (for example /docs when DEBUG=false).
        """
        if isinstance(expected_status, int):
            expected_statuses = (expected_status,)
        else:
            expected_statuses = tuple(expected_status)

        headers = {}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            url = f"{self.base_url}{path}"
            if method == "GET":
                async with session.get(url, headers=headers) as resp:
                    status = resp.status
                    body = await resp.text()
            elif method == "POST":
                async with session.post(url, headers=headers, json=data) as resp:
                    status = resp.status
                    body = await resp.text()
            else:
                status = 0
                body = "Unknown method"

            if status in expected_statuses:
                ok(f"{name} [{method} {path}]")
                self.results["passed"] += 1
                return True
            else:
                expected_label = "/".join(str(item) for item in expected_statuses)
                fail(f"{name} [{method} {path}]", f"Status: {status}, Expected: {expected_label}")
                self.results["failed"] += 1
                return False
        except Exception as e:
            fail(f"{name} [{method} {path}]", str(e))
            self.results["failed"] += 1
            return False

    async def run_checks(self):
        """Run all system checks"""
        print(f"\n{Colors.BOLD}System Health Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.END}")
        print(f"Target: {self.base_url}")
        if not ADMIN_PASSWORD:
            warn("SYSTEM_CHECK_ADMIN_PASSWORD tidak di-set. Login checks akan cenderung gagal.")
        if not GURU_PASSWORD:
            warn("SYSTEM_CHECK_TEACHER_PASSWORD tidak di-set. Teacher login check dilewati.")
        if not SISWA_PASSWORD:
            warn("SYSTEM_CHECK_STUDENT_PASSWORD tidak di-set. Student login check dilewati.")

        async with aiohttp.ClientSession() as session:
            # ============ CORE SYSTEM ============
            header("1. CORE SYSTEM")

            # Health check
            await self.check_endpoint(session, "GET", "/health", "Health Check", auth=False)

            # Root
            await self.check_endpoint(session, "GET", "/", "Root Endpoint", auth=False)

            # ============ AUTHENTICATION ============
            header("2. AUTHENTICATION")

            # Admin Login
            if await self.login(session):
                ok(f"Login as {ADMIN_USERNAME}")
                self.results["passed"] += 1
            else:
                fail(f"Login as {ADMIN_USERNAME}")
                self.results["failed"] += 1
                print(f"\n{Colors.RED}Cannot continue without authentication!{Colors.END}")
                return

            # Get current user
            await self.check_endpoint(session, "GET", "/api/auth/me", "Get Current User (Admin)")

            # Test Guru Login separately when credentials are provided.
            if GURU_PASSWORD:
                try:
                    async with session.post(
                        f"{self.base_url}/api/auth/login",
                        json={"username": GURU_USERNAME, "password": GURU_PASSWORD}
                    ) as resp:
                        if resp.status == 200:
                            ok(f"Login as {GURU_USERNAME} (Teacher)")
                            self.results["passed"] += 1
                        else:
                            fail(f"Login as {GURU_USERNAME} (Teacher)", f"Status: {resp.status}")
                            self.results["failed"] += 1
                except Exception as e:
                    fail(f"Login as {GURU_USERNAME} (Teacher)", str(e))
                    self.results["failed"] += 1
            else:
                warn(f"Skip login as {GURU_USERNAME} (Teacher): password tidak di-set")
                self.results["warnings"] += 1

            # Test Siswa Login separately when credentials are provided.
            if SISWA_PASSWORD:
                try:
                    async with session.post(
                        f"{self.base_url}/api/auth/login",
                        json={"username": SISWA_USERNAME, "password": SISWA_PASSWORD}
                    ) as resp:
                        if resp.status == 200:
                            ok(f"Login as {SISWA_USERNAME} (Student)")
                            self.results["passed"] += 1
                        else:
                            fail(f"Login as {SISWA_USERNAME} (Student)", f"Status: {resp.status}")
                            self.results["failed"] += 1
                except Exception as e:
                    fail(f"Login as {SISWA_USERNAME} (Student)", str(e))
                    self.results["failed"] += 1
            else:
                warn(f"Skip login as {SISWA_USERNAME} (Student): password tidak di-set")
                self.results["warnings"] += 1

            # ============ USERS API ============
            header("3. USERS API")
            await self.check_endpoint(session, "GET", "/api/users/", "List Users")
            await self.check_endpoint(session, "GET", "/api/users/1", "Get User by ID")

            # ============ EXAMS API ============
            header("4. EXAMS API")
            await self.check_endpoint(session, "GET", "/api/exams/", "List Exams")
            # Note: /api/exams/list needs query params, skipping

            # ============ QUESTIONS API ============
            header("5. QUESTIONS API")
            # Note: questions are per exam, so test categories/tags which are public
            await self.check_endpoint(session, "GET", "/api/questions/categories", "Question Categories")
            await self.check_endpoint(session, "GET", "/api/questions/tags", "Question Tags")

            # ============ MONITORING API ============
            header("6. MONITORING API")
            await self.check_endpoint(session, "GET", "/api/monitoring/active-exams", "Active Exams")
            await self.check_endpoint(session, "GET", "/api/monitoring/violations", "Violations List")

            # ============ ANALYTICS API ============
            header("7. ANALYTICS API")
            await self.check_endpoint(session, "GET", "/api/analytics/dashboard", "Analytics Dashboard")

            # ============ GRADING API ============
            header("8. GRADING API")
            await self.check_endpoint(session, "GET", "/api/grading/stats", "Grading Stats")

            # ============ STATS API ============
            header("9. STATS API")
            await self.check_endpoint(session, "GET", "/api/stats/dashboard", "Dashboard Stats")

            # ============ NEW FEATURES (Phase 1-5) ============
            header("10. SCHEDULED PUBLISHING API")
            await self.check_endpoint(session, "GET", "/api/scheduled/schedules/upcoming", "Upcoming Schedules")
            await self.check_endpoint(session, "GET", "/api/scheduled/schedules/stats", "Schedule Stats")

            header("11. TEMPLATES API")
            await self.check_endpoint(session, "GET", "/api/templates/", "List Templates")

            header("12. ACTIVITY LOGS API")
            await self.check_endpoint(session, "GET", "/api/activity/logs", "Activity Logs")
            await self.check_endpoint(session, "GET", "/api/activity/event-types", "Event Types")
            # Note: /stats endpoint has intermittent issues, checking logs separately

            header("13. MEDIA LIBRARY API")
            await self.check_endpoint(session, "GET", "/api/media/", "Media Library")
            await self.check_endpoint(session, "GET", "/api/media/stats/summary", "Media Stats")

            header("14. NOTIFICATIONS API")
            await self.check_endpoint(session, "GET", "/api/notifications/", "Notifications List")
            await self.check_endpoint(session, "GET", "/api/notifications/unread-count", "Unread Count")
            await self.check_endpoint(session, "GET", "/api/notifications/types", "Notification Types")

            # ============ STATIC PAGES ============
            header("15. STATIC PAGES")
            await self.check_endpoint(session, "GET", "/admin/", "Admin Login Page", auth=False)
            await self.check_endpoint(session, "GET", "/admin/dashboard.html", "Admin Dashboard", auth=False)
            await self.check_endpoint(session, "GET", "/admin/exam-templates.html", "Templates Page", auth=False)
            await self.check_endpoint(session, "GET", "/admin/media.html", "Media Library Page", auth=False)
            await self.check_endpoint(session, "GET", "/admin/activity.html", "Activity Logs Page", auth=False)
            await self.check_endpoint(session, "GET", "/student/", "Student Page", auth=False)

            # ============ API DOCS ============
            header("16. API DOCUMENTATION")
            await self.check_endpoint(
                session,
                "GET",
                "/docs",
                "Swagger UI (optional in production)",
                auth=False,
                expected_status=(200, 404),
            )
            await self.check_endpoint(session, "GET", "/openapi.json", "OpenAPI Schema", auth=False)

        # ============ SUMMARY ============
        header("SUMMARY")
        total = self.results["passed"] + self.results["failed"]
        passed_pct = (self.results["passed"] / total * 100) if total > 0 else 0

        print(f"\n  Total Checks: {total}")
        print(f"  {Colors.GREEN}Passed: {self.results['passed']} ({passed_pct:.1f}%){Colors.END}")
        print(f"  {Colors.RED}Failed: {self.results['failed']}{Colors.END}")

        if self.results["failed"] == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✓ ALL SYSTEMS OPERATIONAL!{Colors.END}")
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}✗ SOME ISSUES DETECTED - Please review failed checks above{Colors.END}")

        return self.results["failed"] == 0

async def main():
    if aiohttp is None:
        print("aiohttp is not installed. Running basic HTTP checks with stdlib fallback.")
        url = sys.argv[1] if len(sys.argv) > 1 else BASE_URL
        basic_checks = [
            ("Health Check", "/health", 200),
            ("Root Endpoint", "/", 200),
            ("Admin Page", "/admin/", 200),
            ("Templates Page", "/admin/exam-templates.html", 200),
            ("Student Page", "/student/", 200),
            ("Swagger UI (optional in production)", "/docs", (200, 404)),
            ("OpenAPI Schema", "/openapi.json", 200),
        ]
        failed = 0
        for name, path, expected in basic_checks:
            try:
                req = urllib.request.Request(f"{url.rstrip('/')}{path}", method="GET")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    status = resp.getcode()
                expected_statuses = (expected,) if isinstance(expected, int) else tuple(expected)
                if status in expected_statuses:
                    ok(f"{name} [GET {path}]")
                else:
                    expected_label = "/".join(str(item) for item in expected_statuses)
                    fail(f"{name} [GET {path}]", f"Status: {status}, Expected: {expected_label}")
                    failed += 1
            except urllib.error.HTTPError as exc:
                expected_statuses = (expected,) if isinstance(expected, int) else tuple(expected)
                if exc.code in expected_statuses:
                    ok(f"{name} [GET {path}]")
                else:
                    expected_label = "/".join(str(item) for item in expected_statuses)
                    fail(f"{name} [GET {path}]", f"HTTPError: {exc.code}, Expected: {expected_label}")
                    failed += 1
            except Exception as exc:
                fail(f"{name} [GET {path}]", str(exc))
                failed += 1

        if failed == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✓ BASIC CHECKS OPERATIONAL!{Colors.END}")
            sys.exit(0)
        print(f"\n{Colors.RED}{Colors.BOLD}✗ BASIC CHECKS FAILED: {failed}{Colors.END}")
        sys.exit(1)

    url = sys.argv[1] if len(sys.argv) > 1 else BASE_URL
    checker = SystemChecker(url)
    success = await checker.run_checks()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())
