"""Each step writes a readable report of what it did into runs/<date>/<step>/report.md."""

from datetime import date
from pathlib import Path

from common.runlog import STEPS


def step_folder(root: Path, run_date: date, step: int) -> Path:
    folder = root / "runs" / run_date.isoformat() / f"{step:02d}_{STEPS[step]}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def write_report(root: Path, run_date: date, step: int, lines: list[str]) -> Path:
    path = step_folder(root, run_date, step) / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
