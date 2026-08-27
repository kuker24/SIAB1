from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JOIN_NATIVE = (ROOT / "go" / "internal" / "exam" / "join_native.go").read_text(encoding="utf-8")
JOIN_SQL = (ROOT / "go" / "internal" / "persistence" / "join_native.go").read_text(
    encoding="utf-8"
)
HTTP = (ROOT / "go" / "internal" / "exam" / "http.go").read_text(encoding="utf-8")
NGINX = (ROOT / "docker" / "nginx.production.conf").read_text(encoding="utf-8")
START = (ROOT / "go" / "internal" / "exam" / "start_native.go").read_text(encoding="utf-8")


def test_join_is_native_read_only_and_not_proxied() -> None:
    assert "func (d deps) joinExam" in JOIN_NATIVE
    assert "d.proxyExamWrite" not in JOIN_NATIVE
    assert "d.tryFallback" not in JOIN_NATIVE
    assert "Database tidak tersedia" in JOIN_NATIVE
    assert "joinService" in JOIN_NATIVE
    assert 'mux.HandleFunc("POST /api/exams/join", d.joinExam)' in HTTP


def test_join_sql_matches_fastapi_projection() -> None:
    assert "FROM exams e" in JOIN_SQL
    assert "LookupJoinUser" in JOIN_SQL
    assert "JOIN users u ON u.id = e.creator_id" in JOIN_SQL
    assert "e.access_token = $1" in JOIN_SQL
    assert "is_deleted" not in JOIN_SQL
    assert "SELECT COUNT(*) FROM questions WHERE exam_id = $1" in JOIN_SQL
    assert "selectinload" not in JOIN_SQL
    assert "INSERT" not in JOIN_SQL
    assert "UPDATE" not in JOIN_SQL
    assert "BEGIN" not in JOIN_SQL
    assert "password_hash" not in JOIN_SQL
    assert "builder_settings" not in JOIN_SQL


def test_join_does_not_change_start_admission() -> None:
    assert "START_DB_ADMISSION_LIMIT" not in JOIN_NATIVE
    assert "func (d deps) startExam" in START
    assert "location = /api/exams/join" in NGINX
    join_loc = NGINX.split("location = /api/exams/join", 1)[1].split("location ", 1)[0]
    assert "proxy_pass http://$join_backend;" in join_loc
