"""Tests for papermind chat command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import frontmatter
import httpx
from typer.testing import CliRunner

from papermind.cli.main import app

runner = CliRunner()


def _make_kb_with_papers(tmp_path: Path) -> Path:
    """Create a KB with papers that have rich metadata."""
    kb = tmp_path / "kb"
    runner.invoke(app, ["init", str(kb)])

    papers_dir = kb / "papers" / "hydrology"
    papers_dir.mkdir(parents=True)

    for i, (title, doi, abstract) in enumerate(
        [
            (
                "SWAT Calibration Guide",
                "10.1/swat",
                "A guide to calibrating SWAT models for watershed simulation.",
            ),
            (
                "LSTM for Streamflow",
                "10.1/lstm",
                "Using LSTM networks for streamflow prediction.",
            ),
        ]
    ):
        slug = f"paper-{i}"
        d = papers_dir / slug
        d.mkdir()
        post = frontmatter.Post(f"# {title}\n\nContent.")
        post.metadata = {
            "type": "paper",
            "id": f"paper-{slug}",
            "title": title,
            "topic": "hydrology",
            "doi": doi,
            "abstract": abstract,
            "cites": [f"10.1/ref-{i}"],
            "cited_by": [f"10.1/citer-{i}"],
            "tags": ["swat", "calibration"] if i == 0 else ["lstm"],
        }
        (d / "paper.md").write_text(frontmatter.dumps(post))

    catalog = [
        {
            "id": f"paper-paper-{i}",
            "type": "paper",
            "title": t,
            "path": f"papers/hydrology/paper-{i}/paper.md",
            "topic": "hydrology",
            "doi": d,
        }
        for i, (t, d, _) in enumerate(
            [
                ("SWAT Calibration Guide", "10.1/swat", ""),
                ("LSTM for Streamflow", "10.1/lstm", ""),
            ]
        )
    ]
    (kb / "catalog.json").write_text(json.dumps(catalog))
    return kb


def _mock_ollama_stream(chunks: list[str]) -> MagicMock:
    """Build a mock httpx streaming response from token chunks."""
    lines = []
    for token in chunks:
        lines.append(json.dumps({"response": token, "done": False}))
    lines.append(json.dumps({"response": "", "done": True}))

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_lines = MagicMock(return_value=iter(lines))
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_chat_streams_response(tmp_path: Path) -> None:
    """Chat should stream tokens from ollama."""
    kb = _make_kb_with_papers(tmp_path)
    mock_resp = _mock_ollama_stream(["Hello", " world", "!"])

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_resp)
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("papermind.cli.chat.httpx.Client", return_value=mock_client):
        result = runner.invoke(
            app,
            [
                "--kb",
                str(kb),
                "chat",
                "What is SWAT?",
                "--topic",
                "hydrology",
            ],
        )

    assert result.exit_code == 0
    assert "Hello world!" in result.output


def test_chat_without_topic(tmp_path: Path) -> None:
    """Chat without --topic should still work (no context)."""
    kb = _make_kb_with_papers(tmp_path)
    mock_resp = _mock_ollama_stream(["Answer"])

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_resp)
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("papermind.cli.chat.httpx.Client", return_value=mock_client):
        result = runner.invoke(
            app,
            ["--kb", str(kb), "chat", "What is hydrology?"],
        )

    assert result.exit_code == 0
    assert "Answer" in result.output


def test_chat_ollama_not_running(tmp_path: Path) -> None:
    """Should show helpful error when ollama is not reachable."""
    kb = _make_kb_with_papers(tmp_path)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(side_effect=httpx.ConnectError("refused"))
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("papermind.cli.chat.httpx.Client", return_value=mock_client):
        result = runner.invoke(
            app,
            ["--kb", str(kb), "chat", "test question"],
        )

    assert result.exit_code == 1
    assert "ollama" in result.output.lower()


def test_chat_sends_context_to_llm(tmp_path: Path) -> None:
    """Verify the system prompt includes KB briefing content."""
    kb = _make_kb_with_papers(tmp_path)
    mock_resp = _mock_ollama_stream(["OK"])

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_resp)
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("papermind.cli.chat.httpx.Client", return_value=mock_client):
        runner.invoke(
            app,
            [
                "--kb",
                str(kb),
                "chat",
                "Tell me about SWAT",
                "--topic",
                "hydrology",
                "--model",
                "mistral",
            ],
        )

    # Check the payload sent to ollama
    call_args = mock_client.stream.call_args
    payload = call_args.kwargs.get("json") or call_args[1].get("json")
    assert payload["model"] == "mistral"
    assert "SWAT" in payload["system"]
    assert "Knowledge Base Context" in payload["system"]


def test_chat_empty_topic_warns(tmp_path: Path) -> None:
    """Non-existent topic should warn but proceed."""
    kb = _make_kb_with_papers(tmp_path)
    mock_resp = _mock_ollama_stream(["OK"])

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_resp)
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("papermind.cli.chat.httpx.Client", return_value=mock_client):
        result = runner.invoke(
            app,
            [
                "--kb",
                str(kb),
                "chat",
                "question",
                "--topic",
                "nonexistent",
            ],
        )

    assert result.exit_code == 0
    assert "No papers found" in result.output
