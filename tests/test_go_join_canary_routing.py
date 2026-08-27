from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NGINX = (ROOT / "docker" / "nginx.production.conf").read_text(encoding="utf-8")
OFF = (ROOT / "docker" / "nginx.join-canary-off.conf").read_text(encoding="utf-8")
ACTIVE = (ROOT / "docker" / "nginx.join-canary-5pct.conf").read_text(encoding="utf-8")
RUNTIME = (ROOT / "runtime_control" / "nginx.join-canary.conf").read_text(encoding="utf-8")
START_RUNTIME = (ROOT / "runtime_control" / "nginx.start-canary.conf").read_text(
    encoding="utf-8"
)
START_OFF = (ROOT / "docker" / "nginx.start-canary-off.conf").read_text(encoding="utf-8")


def test_runtime_join_canary_defaults_off() -> None:
    assert RUNTIME == OFF
    assert "split_clients" not in OFF
    assert "default fastapi;" in OFF
    assert START_RUNTIME == START_OFF


def test_stage1_is_stable_five_percent_join_only() -> None:
    assert 'split_clients "$http_authorization"' in ACTIVE
    assert "5% go;" in ACTIVE
    assert "~^/api/exams/join(\\?|$) $go_join_cohort;" in ACTIVE
    assert "default fastapi;" in ACTIVE
    assert "/start" not in ACTIVE
    assert "/answer" not in ACTIVE
    assert "/autosave" not in ACTIVE
    assert "/submit" not in ACTIVE


def test_join_upstream_uses_shared_go_with_fastapi_backup() -> None:
    assert "include /etc/nginx/join-canary.conf;" in NGINX
    assert "proxy_pass http://$join_backend;" in NGINX
    assert 'jr="$go_join_canary"' in NGINX
    join_loc = NGINX.split("location = /api/exams/join", 1)[1].split("location ", 1)[0]
    assert "proxy_pass http://$join_backend;" in join_loc
    assert "go_start_backend" not in join_loc


def test_join_rollout_maps_are_join_only() -> None:
    docker = ROOT / "docker"
    for name, pct in (("10pct", "10%"), ("25pct", "25%"), ("50pct", "50%"), ("75pct", "75%")):
        text = (docker / f"nginx.join-canary-{name}.conf").read_text(encoding="utf-8")
        assert 'split_clients "$http_authorization"' in text
        assert f"{pct} go;" in text
        assert "~^/api/exams/join(\\?|$) $go_join_cohort;" in text
        assert "/start" not in text
        assert "/answer" not in text
        assert "/submit" not in text
    full = (docker / "nginx.join-canary-100pct.conf").read_text(encoding="utf-8")
    assert "split_clients" not in full
    assert "~^/api/exams/join(\\?|$) go;" in full
    assert "default fastapi;" in full
