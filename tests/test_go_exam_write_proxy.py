from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAM = ROOT / "go" / "internal" / "exam"


def test_non_start_student_exam_write_handlers_proxy_instead_of_local_mutation() -> None:
    http_src = (EXAM / "http.go").read_text(encoding="utf-8")
    start_src = (EXAM / "start_native.go").read_text(encoding="utf-8")
    submit_src = (EXAM / "submit.go").read_text(encoding="utf-8")
    runtime_src = (EXAM / "runtime.go").read_text(encoding="utf-8")

    assert "func (d deps) proxyExamWrite" in http_src
    for src, name in (
        (http_src, "autoSave"),
        (http_src, "submitAnswer"),
        (submit_src, "submitExam"),
        (runtime_src, "autoSaveBatch"),
        (runtime_src, "journalSync"),
        (runtime_src, "logViolation"),
    ):
        marker = f"func (d deps) {name}(w http.ResponseWriter, r *http.Request) {{"
        assert marker in src, name
        body = src.split(marker, 1)[1].split("\n}", 1)[0]
        assert "d.proxyExamWrite(w, r)" in body, name

    assert "UpsertAnswer" not in http_src
    assert "UpsertAnswer" not in runtime_src
    start_fn = start_src.split("func (d deps) startExam", 1)[1].split("\n}", 1)[0]
    assert "d.proxyExamWrite(w, r)" not in start_fn
    assert "BeginSubmit" not in submit_src
    assert "LogViolation" not in runtime_src


def test_pgbouncer_json_and_pool_settings_are_pinned() -> None:
    store = (ROOT / "go" / "internal" / "persistence" / "persistence.go").read_text(
        encoding="utf-8"
    )
    start_sql = (ROOT / "go" / "internal" / "persistence" / "start_native.go").read_text(
        encoding="utf-8"
    )
    assert "QueryExecModeSimpleProtocol" in store
    assert "StatementCacheCapacity = 0" in store
    assert "pgPoolMaxConns int32 = 4" in store
    assert start_sql.count("string(payload)") == 2
