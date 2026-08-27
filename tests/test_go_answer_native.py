from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANSWER = (ROOT / "go" / "internal" / "exam" / "answer_native.go").read_text(encoding="utf-8")
SQL = (ROOT / "go" / "internal" / "persistence" / "answer_native.go").read_text(encoding="utf-8")
HTTP = (ROOT / "go" / "internal" / "exam" / "http.go").read_text(encoding="utf-8")
NGINX = (ROOT / "docker" / "nginx.production.conf").read_text(encoding="utf-8")


def test_answer_is_native_direct_write() -> None:
    assert "func (d deps) submitAnswer" in ANSWER
    assert "d.proxyExamWrite" not in ANSWER
    assert "WriteSingleAnswerDirect" in ANSWER
    assert "pg_advisory_xact_lock" in SQL
    assert "ON CONFLICT (session_id, question_id) DO UPDATE" in SQL
    assert 'mux.HandleFunc("POST /api/exams/submit-answer", d.submitAnswer)' in HTTP


def test_answer_does_not_change_start_or_join_routing() -> None:
    start = NGINX.split("location ~ ^/api/exams/[0-9]+/start$", 1)[1].split("location ", 1)[0]
    assert "proxy_pass http://$start_backend;" in start
    join = NGINX.split("location = /api/exams/join", 1)[1].split("location ", 1)[0]
    assert "proxy_pass http://$join_backend;" in join
    answer = NGINX.split("location = /api/exams/submit-answer", 1)[1].split("location ", 1)[0]
    assert "proxy_pass http://$answer_backend;" in answer
