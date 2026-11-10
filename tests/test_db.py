import json
import sqlite3
from contextlib import closing

from fastapi.testclient import TestClient

from app.main import app


def test_legacy_eligibility_migration_preserves_saved_assessments(tmp_path, monkeypatch):
    database = tmp_path / "legacy.db"
    monkeypatch.setenv("APP_DB", str(database))
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("""
            CREATE TABLE recommendations (
                recommendation_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                student_id TEXT NOT NULL,
                profile_version INTEGER NOT NULL,
                opportunity_id TEXT NOT NULL,
                opportunity_version INTEGER NOT NULL,
                method_version TEXT NOT NULL,
                score INTEGER NOT NULL,
                compatible INTEGER NOT NULL,
                reasons TEXT NOT NULL,
                gaps TEXT NOT NULL,
                unknowns TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        assessments = [
            ("REC-interest", "OP-031", 10, 1, ["Interests: not provided"]),
            ("REC-eligible", "OP-032", 2, 1, []),
            ("REC-unknown", "OP-028", 99, 1, ["Availability: Needs checking (dates missing)"]),
            ("REC-ineligible", "OP-033", 100, 0, []),
        ]
        for rec_id, opportunity_id, score, compatible, unknowns in assessments:
            conn.execute(
                "INSERT INTO recommendations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rec_id, "legacy-run", "COOP-B001", 7, opportunity_id, 9,
                 "rules-v1", score, compatible, '["Saved reason"]', '[]',
                 json.dumps(unknowns), "2026-11-10T00:00:00+00:00"),
            )

    # Repeated startup must preserve historical versions/explanations and be idempotent.
    for _ in range(2):
        with TestClient(app) as client:
            response = client.get("/api/students/COOP-B001/recommendations")
            assert response.status_code == 200
            results = response.json()
            assert [r["recommendation_id"] for r in results] == [a[0] for a in assessments]
            assert [r["eligibility"] for r in results] == ["eligible", "eligible", "unknown", "ineligible"]
            assert [r["compatible"] for r in results] == [True, True, False, False]
            for result, assessment in zip(results, assessments):
                assert result["method_version"] == "rules-v1"
                assert result["profile_version"] == 7 and result["opportunity_version"] == 9
                assert result["reasons"] == ["Saved reason"]
                assert result["unknowns"] == assessment[4]

            # The migrated database must also accept new matching runs.
            assert client.post("/api/students/COOP-B002/recommendations").status_code == 200
