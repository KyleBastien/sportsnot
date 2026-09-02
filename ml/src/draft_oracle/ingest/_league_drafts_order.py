"""Draft-order detection helpers for sheet tabs."""

from __future__ import annotations


def detect_draft_order(rows: list[list[str]]) -> dict[str, int] | None:
    """Read the four-manager draft-order list from a round tab's annotation area."""
    runs = [*_horizontal_runs(rows), *_vertical_runs(rows)]
    valid = _valid_manager_runs(runs)
    if not valid:
        return None
    if len(valid) > 1:
        raise ValueError(f"ambiguous draft-order lists detected: {sorted(valid)}")
    order = next(iter(valid))
    return {manager: slot for slot, manager in enumerate(order, start=1)}


def _horizontal_runs(rows: list[list[str]]) -> list[tuple[str, ...]]:
    return [run for row in rows for run in _row_runs(row)]


def _vertical_runs(rows: list[list[str]]) -> list[tuple[str, ...]]:
    ncols = max((len(row) for row in rows), default=0)
    runs: list[tuple[str, ...]] = []
    for col in range(5, ncols):
        runs.extend(_column_runs(rows, col))
    return runs


def _row_runs(row: list[str]) -> list[tuple[str, ...]]:
    runs: list[tuple[str, ...]] = []
    col = 5
    while col < len(row):
        run, col = _consume_row_run(row, col)
        if len(run) >= 4:
            runs.append(tuple(run[:4]))
    return runs


def _column_runs(rows: list[list[str]], col: int) -> list[tuple[str, ...]]:
    runs: list[tuple[str, ...]] = []
    row_index = 0
    while row_index < len(rows):
        run, row_index = _consume_column_run(rows, row_index, col)
        if len(run) >= 4:
            runs.append(tuple(run[:4]))
    return runs


def _consume_row_run(row: list[str], col: int) -> tuple[list[str], int]:
    if not _is_manager_cell(row, col):
        return [], col + 1
    run: list[str] = []
    while col < len(row) and _is_manager_cell(row, col):
        run.append(_canonical_cell(row, col))
        col += 1
    return run, col


def _consume_column_run(
    rows: list[list[str]], row_index: int, col: int
) -> tuple[list[str], int]:
    if not _is_manager_cell(rows[row_index], col):
        return [], row_index + 1
    run: list[str] = []
    while row_index < len(rows) and _is_manager_cell(rows[row_index], col):
        run.append(_canonical_cell(rows[row_index], col))
        row_index += 1
    return run, row_index


def _valid_manager_runs(runs: list[tuple[str, ...]]) -> set[tuple[str, ...]]:
    from draft_oracle.ingest.league_drafts import LEAGUE_MANAGERS

    return {run for run in runs if set(run) == LEAGUE_MANAGERS}


def _is_manager_cell(row: list[str], col: int) -> bool:
    from draft_oracle.ingest.league_drafts import _cell, _is_manager_token

    return _is_manager_token(_cell(row, col))


def _canonical_cell(row: list[str], col: int) -> str:
    from draft_oracle.ingest.league_drafts import _cell, canonical_manager

    return canonical_manager(_cell(row, col))
