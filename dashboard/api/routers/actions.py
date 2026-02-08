"""API routes for heartbeat actions."""

import math

from fastapi import APIRouter, HTTPException, Query

from dashboard.api.database import get_db
from dashboard.api.models import ActionCreateIn, ActionOut, PaginatedActions

router = APIRouter(tags=["actions"])


@router.get("/api/runs/{run_id}/actions", response_model=list[ActionOut])
def get_run_actions(run_id: str):
    """Get all actions for a specific run."""
    with get_db() as conn:
        run = conn.execute(
            "SELECT run_id FROM heartbeat_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        rows = conn.execute(
            "SELECT * FROM heartbeat_actions WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()

    return [
        ActionOut(
            id=row["id"],
            run_id=row["run_id"],
            action_type=row["action_type"],
            target_id=row["target_id"],
            target_title=row["target_title"],
            target_author=row["target_author"],
            detail=row["detail"],
            succeeded=bool(row["succeeded"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.post(
    "/api/runs/{run_id}/actions",
    response_model=list[ActionOut],
    status_code=201,
)
def create_run_actions(run_id: str, actions: list[ActionCreateIn]):
    """Record actions for a run."""
    with get_db() as conn:
        run = conn.execute(
            "SELECT run_id FROM heartbeat_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        created = []
        for action in actions:
            cursor = conn.execute(
                """
                INSERT INTO heartbeat_actions
                    (run_id, action_type, target_id, target_title,
                     target_author, detail, succeeded)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    action.action_type,
                    action.target_id,
                    action.target_title,
                    action.target_author,
                    action.detail,
                    1 if action.succeeded else 0,
                ),
            )
            row = conn.execute(
                "SELECT * FROM heartbeat_actions WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            created.append(
                ActionOut(
                    id=row["id"],
                    run_id=row["run_id"],
                    action_type=row["action_type"],
                    target_id=row["target_id"],
                    target_title=row["target_title"],
                    target_author=row["target_author"],
                    detail=row["detail"],
                    succeeded=bool(row["succeeded"]),
                    created_at=row["created_at"],
                )
            )
        conn.commit()

    return created


@router.get("/api/actions", response_model=PaginatedActions)
def list_actions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    action_type: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    """List all actions with pagination and filtering."""
    conditions = []
    params = []

    if action_type:
        conditions.append("a.action_type = ?")
        params.append(action_type)
    if date_from:
        conditions.append("a.created_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("a.created_at <= ?")
        params.append(date_to)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    with get_db() as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) as total FROM heartbeat_actions a {where}", params
        ).fetchone()
        total = total_row["total"]

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"""
            SELECT * FROM heartbeat_actions a
            {where}
            ORDER BY a.created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        ).fetchall()

    actions = [
        ActionOut(
            id=row["id"],
            run_id=row["run_id"],
            action_type=row["action_type"],
            target_id=row["target_id"],
            target_title=row["target_title"],
            target_author=row["target_author"],
            detail=row["detail"],
            succeeded=bool(row["succeeded"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]

    return PaginatedActions(
        actions=actions,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=max(1, math.ceil(total / per_page)),
    )
