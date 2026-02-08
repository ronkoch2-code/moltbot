"""API routes for heartbeat runs."""

import math

from fastapi import APIRouter, HTTPException, Query

from dashboard.api.database import get_db
from dashboard.api.models import (
    PaginatedRuns,
    RunCreateIn,
    RunDetailOut,
    RunOut,
    RunUpdateIn,
    ActionOut,
)

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _row_to_run(row, action_count: int = 0) -> dict:
    """Convert a sqlite3.Row to a RunOut-compatible dict."""
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "duration_seconds": row["duration_seconds"],
        "exit_code": row["exit_code"],
        "status": row["status"],
        "agent_name": row["agent_name"],
        "script_variant": row["script_variant"],
        "run_number": row["run_number"],
        "summary": row["summary"],
        "error_message": row["error_message"],
        "action_count": action_count,
        "prompt_version_id": row["prompt_version_id"],
        "created_at": row["created_at"],
    }


@router.get("", response_model=PaginatedRuns)
def list_runs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    agent_name: str | None = Query(None),
    search: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    """List heartbeat runs with pagination and filtering."""
    conditions = []
    params = []

    if status:
        conditions.append("r.status = ?")
        params.append(status)
    if agent_name:
        conditions.append("r.agent_name = ?")
        params.append(agent_name)
    if search:
        conditions.append("(r.summary LIKE ? OR r.raw_output LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if date_from:
        conditions.append("r.started_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("r.started_at <= ?")
        params.append(date_to)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    with get_db() as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) as total FROM heartbeat_runs r {where}", params
        ).fetchone()
        total = total_row["total"]

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"""
            SELECT r.*,
                   (SELECT COUNT(*) FROM heartbeat_actions a WHERE a.run_id = r.run_id) as action_count
            FROM heartbeat_runs r
            {where}
            ORDER BY r.started_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        ).fetchall()

    runs = []
    for row in rows:
        run_dict = _row_to_run(row, action_count=row["action_count"])
        runs.append(RunOut(**run_dict))

    return PaginatedRuns(
        runs=runs,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=max(1, math.ceil(total / per_page)),
    )


@router.post("", response_model=RunOut, status_code=201)
def create_run(body: RunCreateIn):
    """Record a new heartbeat run."""
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO heartbeat_runs
                (run_id, started_at, agent_name, script_variant, run_number, raw_output, status)
            VALUES (?, ?, ?, ?, ?, ?, 'running')
            """,
            (
                body.run_id,
                body.started_at,
                body.agent_name,
                body.script_variant,
                body.run_number,
                body.raw_output,
            ),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM heartbeat_runs WHERE run_id = ?", (body.run_id,)
        ).fetchone()

    return RunOut(**_row_to_run(row))


@router.get("/{run_id}", response_model=RunDetailOut)
def get_run(run_id: str):
    """Get a single run with its actions."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM heartbeat_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")

        action_rows = conn.execute(
            "SELECT * FROM heartbeat_actions WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()

    actions = [
        ActionOut(
            id=a["id"],
            run_id=a["run_id"],
            action_type=a["action_type"],
            target_id=a["target_id"],
            target_title=a["target_title"],
            target_author=a["target_author"],
            detail=a["detail"],
            succeeded=bool(a["succeeded"]),
            created_at=a["created_at"],
        )
        for a in action_rows
    ]

    return RunDetailOut(
        **_row_to_run(row, action_count=len(actions)),
        raw_output=row["raw_output"],
        actions=actions,
    )


@router.patch("/{run_id}", response_model=RunOut)
def update_run(run_id: str, body: RunUpdateIn):
    """Update a run (set finished, status, summary, etc.)."""
    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM heartbeat_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Run not found")

        updates = []
        params = []
        for field in ["finished_at", "duration_seconds", "exit_code", "status",
                       "summary", "error_message", "raw_output"]:
            value = getattr(body, field, None)
            if value is not None:
                updates.append(f"{field} = ?")
                params.append(value)

        if updates:
            params.append(run_id)
            conn.execute(
                f"UPDATE heartbeat_runs SET {', '.join(updates)} WHERE run_id = ?",
                params,
            )
            conn.commit()

        row = conn.execute(
            "SELECT * FROM heartbeat_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        action_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM heartbeat_actions WHERE run_id = ?",
            (run_id,),
        ).fetchone()["cnt"]

    return RunOut(**_row_to_run(row, action_count=action_count))
