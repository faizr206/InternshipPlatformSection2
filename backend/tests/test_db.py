import json
import sqlite3
from contextlib import closing

from fastapi.testclient import TestClient

from app.main import app


def test_sprint2_columns_migrate_on_sprint1_databases(tmp_path, monkeypatch):
    """Sprint 1 databases gain the Sprint 2 columns (application statement,
    recommendation AI fields) additively, preserving saved rows."""
    database = tmp_path / "sprint1.db"
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
                created_at TEXT NOT NULL,
                eligibility TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO recommendations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("REC-old", "old-run", "COOP-B001", 1, "OP-028", 2, "rules-v2", 8, 1,
             '["Saved reason"]', '[]', '[]', "2026-11-10T00:00:00+00:00", "eligible"),
        )
        conn.execute("""
            CREATE TABLE applications (
                application_id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL,
                profile_version INTEGER NOT NULL,
                opportunity_id TEXT NOT NULL,
                opportunity_version INTEGER NOT NULL,
                application_status TEXT NOT NULL,
                placement_status TEXT NOT NULL,
                submitted_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO applications VALUES (?,?,?,?,?,?,?,?)",
            ("APP-0001", "COOP-B001", 1, "OP-031", 1, "Submitted", "Not placed",
             "2026-11-10T00:00:00+00:00"),
        )

    with TestClient(app) as client:
        # The legacy recommendation is served with empty AI assistance, rules result intact
        recs = client.get("/api/students/COOP-B001/recommendations").json()
        assert [r["recommendation_id"] for r in recs] == ["REC-old"]
        assert recs[0]["ai_matches"] == [] and recs[0]["ai_method_version"] is None
        assert recs[0]["ai_insights"] is None  # older runs have no stored insights
        assert recs[0]["method_version"] == "rules-v2" and recs[0]["reasons"] == ["Saved reason"]

        # The legacy application survives without a statement and gains an empty history
        apps = client.get("/api/students/COOP-B001/applications").json()
        assert [a["application_id"] for a in apps] == ["APP-0001"]
        assert apps[0]["statement"] is None and apps[0]["history"] == []

        # New Sprint 2 flows work on the migrated database
        new = client.post("/api/applications", json={
            "student_id": "COOP-B001", "opportunity_id": "OP-028",
            "statement": "Migrated database, new application."})
        assert new.status_code == 201
        decision = client.post(f"/api/applications/{new.json()['application_id']}/decisions", json={
            "action": "Under review", "actor_role": "employer"})
        assert decision.status_code == 201


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
