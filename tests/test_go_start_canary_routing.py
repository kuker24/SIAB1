from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NGINX = (ROOT / "docker" / "nginx.production.conf").read_text(encoding="utf-8")
OFF = (ROOT / "docker" / "nginx.start-canary-off.conf").read_text(encoding="utf-8")
ACTIVE = (ROOT / "docker" / "nginx.start-canary-5pct.conf").read_text(encoding="utf-8")
RUNTIME = (ROOT / "runtime_control" / "nginx.start-canary.conf").read_text(
    encoding="utf-8"
)


def test_runtime_canary_defaults_off() -> None:
    assert RUNTIME == OFF
    assert "split_clients" not in OFF
    assert "default fastapi;" in OFF


def test_stage1_is_stable_five_percent_start_only() -> None:
    assert 'split_clients "$http_authorization"' in ACTIVE
    assert "5% go;" in ACTIVE
    assert "~^/api/exams/[0-9]+/start$ $go_start_cohort;" in ACTIVE
    assert "default fastapi;" in ACTIVE


def test_go_upstream_has_fastapi_backup_and_route_logging() -> None:
    assert "include /etc/nginx/start-canary.conf;" in NGINX
    assert "server go_server:8000 resolve max_fails=1" in NGINX
    assert "server api:8000 resolve backup;" in NGINX
    assert 'sr="$go_start_canary"' in NGINX
    assert 'ur="$upstream_http_x_siab_replica"' in NGINX
    assert "location ^~ /internal/" in NGINX


def test_start_rollout_maps_are_start_only() -> None:
    docker = ROOT / "docker"
    for name, pct in (("10pct", "10%"), ("25pct", "25%"), ("50pct", "50%"), ("75pct", "75%")):
        text = (docker / f"nginx.start-canary-{name}.conf").read_text(encoding="utf-8")
        assert 'split_clients "$http_authorization"' in text
        assert f"{pct} go;" in text
        assert "~^/api/exams/[0-9]+/start$ $go_start_cohort;" in text
        assert "default fastapi;" in text
        assert "/join" not in text
        assert "/answer" not in text
        assert "/autosave" not in text
        assert "/submit" not in text
    full = (docker / "nginx.start-canary-100pct.conf").read_text(encoding="utf-8")
    assert "split_clients" not in full
    assert "~^/api/exams/[0-9]+/start$ go;" in full
    assert "default fastapi;" in full
