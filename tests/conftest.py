from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from context_orchestrator.agent_interface.api import ContextService
from context_orchestrator.telemetry.events import MemoryTelemetry

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PROJECT = REPO_ROOT / "examples" / "sample_project"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A private copy of the sample project that tests may modify."""
    dest = tmp_path / "project"
    shutil.copytree(SAMPLE_PROJECT, dest, ignore=shutil.ignore_patterns(".ctxo", "__pycache__"))
    return dest


@pytest.fixture
def telemetry() -> MemoryTelemetry:
    return MemoryTelemetry()


@pytest.fixture
def service(project: Path, tmp_path: Path, telemetry: MemoryTelemetry) -> Iterator[ContextService]:
    svc = ContextService(project, state_dir=tmp_path / "state", telemetry=telemetry)
    svc.ingest()
    yield svc
    svc.close()
