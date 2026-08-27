from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
NGINX_CONF = (ROOT / "docker" / "nginx.production.conf").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")

CRITICAL_JS = (
    "/static/js/exam-system.js",
    "/static/js/api.js",
    "/static/js/auth.js",
    "/static/js/exam-builder.js",
)


def _location_block(path: str) -> str:
    if path.startswith("/static/") and path.endswith("/") and path != "/static/":
        pattern = rf"location \^~ {re.escape(path)} \{{([\s\S]*?)\n        \}}"
    elif path.startswith("="):
        pattern = rf"location = {re.escape(path[2:])} \{{([\s\S]*?)\n        \}}"
    else:
        pattern = rf"location {re.escape(path)} \{{([\s\S]*?)\n        \}}"
    match = re.search(pattern, NGINX_CONF)
    assert match is not None, f"location {path} not found"
    return match.group(1)


def test_critical_exam_js_served_from_disk_with_no_store() -> None:
    for script in CRITICAL_JS:
        block = _location_block(f"= {script}")
        assert "proxy_pass" not in block
        assert "alias /usr/share/nginx/html" in block
        assert "no-store" in block


def test_static_prefix_and_uploads_are_aliased_not_proxied() -> None:
    uploads = _location_block("/static/uploads/")
    assert "proxy_pass" not in uploads
    assert "alias /usr/share/nginx/html/static/uploads/" in uploads
    assert "immutable" not in uploads

    static = _location_block("/static/")
    assert "proxy_pass" not in static
    assert "alias /usr/share/nginx/html/static/" in static


def test_stub_status_is_internal_and_not_on_public_vhost() -> None:
    assert "listen 8081;" in NGINX_CONF
    assert "location = /nginx_status" in NGINX_CONF
    public_listen = NGINX_CONF.split("listen 80 default_server;")[1]
    public_server = public_listen.split("\n    }", 1)[0]
    assert "location = /nginx_status" not in public_server
    status_server = NGINX_CONF.split("listen 8081;")[1]
    assert "stub_status;" in status_server
    assert "deny all;" in status_server


def test_compose_defines_prometheus_exporters_on_internal_network() -> None:
    for service in (
        "postgres-exporter:",
        "redis-exporter:",
        "nginx-exporter:",
        "node-exporter:",
    ):
        assert service in COMPOSE
    assert "0.0.0.0:9100" not in COMPOSE
    assert "0.0.0.0:9187" not in COMPOSE
    assert "nginx:8081/nginx_status" in COMPOSE
    assert "DATA_SOURCE_NAME: postgresql://examuser:${DB_PASSWORD" in COMPOSE


def test_only_exam_start_canary_can_reach_go() -> None:
    assert "go_server:" in COMPOSE
    assert 'profiles: ["native-lean"]' in COMPOSE
    assert "PYTHON_UPSTREAM=http://api:8000" in COMPOSE
    assert "server go_server:8000" in NGINX_CONF
    start = _location_block("~ ^/api/exams/[0-9]+/start$")
    assert "proxy_pass http://$start_backend" in start
    assert "http_500" in start
    routed = (
        ("= /api/exams/join", "$join_backend"),
        ("= /api/exams/submit-answer", "$answer_backend"),
        ("= /api/exams/auto-save", "$autosave_backend"),
        ("= /api/exams/auto-save-batch", "$batch_backend"),
        ("= /api/exams/submit", "$submit_backend"),
    )
    for path, backend in routed:
        block = _location_block(path)
        assert f"proxy_pass http://{backend}" in block
        assert "go_server" not in block
    fallback = _location_block("/api/")
    assert "proxy_pass http://fastapi_backend" in fallback
    assert "go_server" not in fallback


def test_go_start_uses_scored_pgbouncer_settings_and_n4() -> None:
    assert "pool_max_conns=4" in COMPOSE
    assert "default_query_exec_mode=simple_protocol" in COMPOSE
    assert "statement_cache_capacity=0" in COMPOSE
    assert "START_DB_ADMISSION_LIMIT=4" in COMPOSE
    assert "SIAB_REPLICA=go-start" in COMPOSE


def test_memory_budget_keeps_burst_workers_and_caps_postgres() -> None:
    assert "shared_buffers=512MB" in COMPOSE
    assert "shared_buffers=2560MB" not in COMPOSE
    assert "maintenance_work_mem=128MB" in COMPOSE
    assert "shm_size: 576mb" in COMPOSE
    assert "memory: 1536M" in COMPOSE
    assert "--workers ${WORKERS:-2}" in COMPOSE
    assert "worker_processes 4;" in NGINX_CONF
    assert "worker_connections 8192;" in NGINX_CONF
    assert "worker_processes auto;" not in NGINX_CONF
