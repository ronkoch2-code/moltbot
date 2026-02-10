"""API routes for heartbeat actions."""

import math

from fastapi import APIRouter, Depends, HTTPException, Query

from dashboard.api.auth import require_auth
from dashboard.api.database import get_db
from dashboard.api.models import ActionCreateIn, ActionOut, PaginatedActions

router = APIRouter(tags=["actions"], dependencies=[Depends(require_auth)])


@router.get("/api/runs/{run_id}/actions", response_model=list[ActionOut])
def get_run_actions(run_id: str):
    """Get all actions for a specific run."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT run_id FROM heartbeat_runs WHERE run_id = %s", (run_id,)
        )
        run = cur.fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        cur.execute(
            "SELECT * FROM heartbeat_actions WHERE run_id = %s ORDER BY id",
            (run_id,),
        )
        rows = cur.fetchall()

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
            created_at=str(row["created_at"]),
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
        cur = conn.cursor()
        cur.execute(
            "SELECT run_id FROM heartbeat_runs WHERE run_id = %s", (run_id,)
        )
        run = cur.fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        created = []
        for action in actions:
            cur.execute(
                """
                INSERT INTO heartbeat_actions
                    (run_id, action_type, target_id, target_title,
                     target_author, detail, succeeded)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    run_id,
                    action.action_type,
                    action.target_id,
                    action.target_title,
                    action.target_author,
                    action.detail,
                    action.succeeded,
                ),
            )
            row = cur.fetchone()
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
                    created_at=str(row["created_at"]),
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
        conditions.append("a.action_type = %s")
        params.append(action_type)
    if date_from:
        conditions.append("a.created_at >= %s::timestamptz")
        params.append(date_from)
    if date_to:
        conditions.append("a.created_at <= %s::timestamptz")
        params.append(date_to)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) as total FROM heartbeat_actions a {where}", params
        )
        total = cur.fetchone()["total"]

        offset = (page - 1) * per_page
        cur.execute(
            f"""
            SELECT * FROM heartbeat_actions a
            {where}
            ORDER BY a.created_at DESC
            LIMIT %s OFFSET %s
            """,
            [*params, per_page, offset],
        )
        rows = cur.fetchall()

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
            created_at=str(row["created_at"]),
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
