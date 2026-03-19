"""Tests for all REST API endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_scan(self, client: TestClient) -> None:
        resp = client.get("/api/v1/search/scan", params={"q": "hydrology"})
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert data["query"] == "hydrology"

    def test_summary(self, client: TestClient) -> None:
        resp = client.get("/api/v1/search/summary", params={"q": "calibration"})
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data

    def test_detail(self, client: TestClient) -> None:
        resp = client.get("/api/v1/search/detail/papers/hydrology/test-paper/paper.md")
        assert resp.status_code == 200
        assert "content" in resp.json()

    def test_detail_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/search/detail/nonexistent.md")
        assert resp.status_code == 404

    def test_detail_path_traversal(self, client: TestClient) -> None:
        resp = client.get("/api/v1/search/detail/../../../etc/passwd")
        assert resp.status_code in (403, 404)  # 404 if resolved path doesn't exist

    def test_scan_requires_query(self, client: TestClient) -> None:
        resp = client.get("/api/v1/search/scan")
        assert resp.status_code == 422  # validation error


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class TestCatalog:
    def test_list_papers(self, client: TestClient) -> None:
        resp = client.get("/api/v1/papers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

    def test_list_papers_filter_topic(self, client: TestClient) -> None:
        resp = client.get("/api/v1/papers", params={"topic": "hydrology"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    def test_list_papers_filter_empty_topic(self, client: TestClient) -> None:
        resp = client.get("/api/v1/papers", params={"topic": "nonexistent"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_get_paper(self, client: TestClient) -> None:
        resp = client.get("/api/v1/papers/paper-test-2020")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test Paper on Hydrology"
        assert data["doi"] == "10.1234/test2020"
        assert data["year"] == 2020

    def test_get_paper_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/papers/paper-nonexistent")
        assert resp.status_code == 404

    def test_stats(self, client: TestClient) -> None:
        resp = client.get("/api/v1/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["papers"] >= 2

    def test_topics(self, client: TestClient) -> None:
        resp = client.get("/api/v1/topics")
        assert resp.status_code == 200
        assert "hydrology" in resp.json()["topics"]

    def test_packages(self, client: TestClient) -> None:
        resp = client.get("/api/v1/packages")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0  # no packages in test KB


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class TestSessions:
    def test_create_and_read(self, client: TestClient) -> None:
        # Create
        resp = client.post("/api/v1/sessions", json={"name": "test session"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test session"
        sid = data["id"]

        # Add entry
        resp = client.post(
            f"/api/v1/sessions/{sid}/entries",
            json={"content": "Found a paper", "agent": "test-agent"},
        )
        assert resp.status_code == 200

        # Read
        resp = client.get(f"/api/v1/sessions/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["content"] == "Found a paper"

    def test_list_sessions(self, client: TestClient) -> None:
        client.post("/api/v1/sessions", json={"name": "session a"})
        client.post("/api/v1/sessions", json={"name": "session b"})

        resp = client.get("/api/v1/sessions")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    def test_close_session(self, client: TestClient) -> None:
        client.post("/api/v1/sessions", json={"name": "closeable"})

        resp = client.post("/api/v1/sessions/closeable/close")
        assert resp.status_code == 200
        assert resp.json()["closed"] is True

        # Adding to closed session should fail
        resp = client.post(
            "/api/v1/sessions/closeable/entries",
            json={"content": "should fail"},
        )
        assert resp.status_code == 404  # ValueError → 404

    def test_duplicate_session(self, client: TestClient) -> None:
        client.post("/api/v1/sessions", json={"name": "unique"})
        resp = client.post("/api/v1/sessions", json={"name": "unique"})
        assert resp.status_code == 409

    def test_read_nonexistent(self, client: TestClient) -> None:
        resp = client.get("/api/v1/sessions/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


class TestAnalysis:
    def test_explain_glossary(self, client: TestClient) -> None:
        resp = client.post("/api/v1/analysis/explain", json={"concept": "CN2"})
        assert resp.status_code == 200
        data = resp.json()
        assert "Curve Number" in data["name"]
        assert data["source"] == "glossary"

    def test_explain_not_found(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/analysis/explain", json={"concept": "nonexistent_xyz"}
        )
        assert resp.status_code == 404

    def test_provenance(self, client: TestClient, tmp_path: Path) -> None:
        src = tmp_path / "model.py"
        src.write_text("# REF: doi:10.1234/test eq.1\ndef f(): pass\n")

        resp = client.post("/api/v1/analysis/provenance", json={"file_path": str(src)})
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_equation_map(self, client: TestClient, tmp_path: Path) -> None:
        src = tmp_path / "model.py"
        src.write_text("def calc(Q, A):\n    return Q / A\n")

        resp = client.post(
            "/api/v1/analysis/equation-map",
            json={
                "equation_latex": "Q = V \\cdot A",
                "file_path": str(src),
                "function_name": "calc",
            },
        )
        assert resp.status_code == 200
        assert len(resp.json()["mappings"]) >= 1

    def test_resolve_refs(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/analysis/resolve-refs",
            json={"text": "See kb:paper-test-2020 for details."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["refs"][0]["found"] is True

    def test_resolve_refs_empty(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/analysis/resolve-refs",
            json={"text": "No references here."},
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ---------------------------------------------------------------------------
# API Diff
# ---------------------------------------------------------------------------


class TestAPIDiff:
    def test_diff(self, client: TestClient, kb: Path) -> None:
        # Create two package versions
        for name, api_text in [
            ("pkg-1.0", "### `connect(host, port)`\n\n### `close()`\n"),
            ("pkg-2.0", "### `connect(host, port, ssl)`\n\n### `send(data)`\n"),
        ]:
            d = kb / "packages" / name
            d.mkdir(parents=True)
            (d / "api.md").write_text(api_text)

        resp = client.get("/api/v1/api-diff/pkg-1.0/pkg-2.0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["removed"]) >= 1  # close removed
        assert len(data["added"]) >= 1  # send added

    def test_diff_missing_package(self, client: TestClient) -> None:
        resp = client.get("/api/v1/api-diff/nonexistent/also-nonexistent")
        assert resp.status_code == 404
