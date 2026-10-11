import json
from pathlib import Path

import pytest

from context_orchestrator.agent_interface.cli import main


def test_ingest_then_request_json(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state = str(tmp_path / "state")
    assert main(["ingest", str(project), "--state-dir", state]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["total_chunks"] > 0 and len(report["added"]) == 18

    assert (
        main(
            [
                "request",
                str(project),
                "--state-dir",
                state,
                "--task",
                "loans table schema returned_at",
                "--kind",
                "schema",
            ]
        )
        == 0
    )
    package = json.loads(capsys.readouterr().out)
    assert package["items"][0]["source"]["path"] == "db/schema.sql"
    assert package["estimated_tokens"]["kind"] == "estimated"


def test_request_from_file_as_markdown(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state = str(tmp_path / "state")
    main(["ingest", str(project), "--state-dir", state])
    capsys.readouterr()
    req = tmp_path / "req.json"
    req.write_text(
        json.dumps(
            {
                "task": "coding conventions for money naming",
                "kinds": ["convention"],
                "agent_id": "reviewer",
            }
        )
    )
    assert (
        main(
            [
                "request",
                str(project),
                "--state-dir",
                state,
                "--request-file",
                str(req),
                "--format",
                "markdown",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert out.startswith("# Context package for: coding conventions")
    assert "docs/conventions.md" in out


def test_request_before_ingest_fails_cleanly(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["request", str(project), "--state-dir", str(tmp_path / "s"), "--task", "x y"])
    assert code == 1
    assert "Run ingest first" in capsys.readouterr().err


def test_missing_project_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ingest", str(tmp_path / "nope")]) == 2
