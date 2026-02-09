"""API routes for security analytics."""

import math

from fastapi import APIRouter, HTTPException, Query

from dashboard.api.database import get_db
from dashboard.api.models import (
    BlockAuthorIn,
    BlockedAuthorOut,
    OddityOut,
    PaginatedBlockedAuthors,
    PaginatedOddities,
    PaginatedSecurityEvents,
    PaginatedToolCalls,
    SecurityEventOut,
    SecurityStatsOut,
    ToolCallOut,
    UnblockAuthorIn,
)

router = APIRouter(prefix="/api/security", tags=["security"])


@router.get("/events", response_model=PaginatedSecurityEvents)
def list_security_events(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    event_type: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    min_risk_score: float | None = Query(None, ge=0.0, le=1.0),
):
    """List security events with pagination and filtering."""
    conditions = []
    params: list = []

    if event_type:
        conditions.append("event_type = %s")
        params.append(event_type)
    if date_from:
        conditions.append("timestamp >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("timestamp <= %s")
        params.append(date_to)
    if min_risk_score is not None:
        conditions.append("risk_score >= %s")
        params.append(min_risk_score)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) as total FROM security_events {where}", params
        )
        total = cur.fetchone()["total"]

        offset = (page - 1) * per_page
        cur.execute(
            f"""SELECT * FROM security_events {where}
                ORDER BY timestamp DESC LIMIT %s OFFSET %s""",
            [*params, per_page, offset],
        )
        rows = cur.fetchall()

    events = [SecurityEventOut(**{k: str(v) if k == "created_at" else v for k, v in row.items()}) for row in rows]
    return PaginatedSecurityEvents(
        events=events,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=max(1, math.ceil(total / per_page)),
    )


@router.get("/events/{event_id}", response_model=SecurityEventOut)
def get_security_event(event_id: int):
    """Get a single security event."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM security_events WHERE id = %s", (event_id,)
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Security event not found")
    return SecurityEventOut(**{k: str(v) if k == "created_at" else v for k, v in row.items()})


@router.get("/tool-calls", response_model=PaginatedToolCalls)
def list_tool_calls(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    tool_name: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    """List tool calls with pagination and filtering."""
    conditions = []
    params: list = []

    if tool_name:
        conditions.append("tool_name = %s")
        params.append(tool_name)
    if date_from:
        conditions.append("timestamp >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("timestamp <= %s")
        params.append(date_to)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) as total FROM tool_calls {where}", params
        )
        total = cur.fetchone()["total"]

        offset = (page - 1) * per_page
        cur.execute(
            f"""SELECT * FROM tool_calls {where}
                ORDER BY timestamp DESC LIMIT %s OFFSET %s""",
            [*params, per_page, offset],
        )
        rows = cur.fetchall()

    tool_calls = [ToolCallOut(**{k: str(v) if k == "created_at" else v for k, v in row.items()}) for row in rows]
    return PaginatedToolCalls(
        tool_calls=tool_calls,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=max(1, math.ceil(total / per_page)),
    )


@router.get("/oddities", response_model=PaginatedOddities)
def list_oddities(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    oddity_type: str | None = Query(None),
    severity: str | None = Query(None),
):
    """List behavior oddities with pagination and filtering."""
    conditions = []
    params: list = []

    if oddity_type:
        conditions.append("oddity_type = %s")
        params.append(oddity_type)
    if severity:
        conditions.append("severity = %s")
        params.append(severity)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) as total FROM behavior_oddities {where}", params
        )
        total = cur.fetchone()["total"]

        offset = (page - 1) * per_page
        cur.execute(
            f"""SELECT * FROM behavior_oddities {where}
                ORDER BY detected_at DESC LIMIT %s OFFSET %s""",
            [*params, per_page, offset],
        )
        rows = cur.fetchall()

    oddities = [OddityOut(**{k: str(v) if k == "created_at" else v for k, v in row.items()}) for row in rows]
    return PaginatedOddities(
        oddities=oddities,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=max(1, math.ceil(total / per_page)),
    )


@router.get("/stats", response_model=SecurityStatsOut)
def get_security_stats():
    """Get aggregate security statistics."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT
                COUNT(*) as total_events,
                SUM(CASE WHEN event_type = 'injection_attempt' THEN 1 ELSE 0 END) as injection_attempts,
                SUM(CASE WHEN event_type = 'unauthorized_access' THEN 1 ELSE 0 END) as unauthorized_access,
                SUM(CASE WHEN event_type = 'suspicious_pattern' THEN 1 ELSE 0 END) as suspicious_patterns,
                AVG(risk_score) as avg_risk_score,
                MAX(risk_score) as max_risk_score
            FROM security_events"""
        )
        event_stats = cur.fetchone()

        cur.execute(
            """SELECT author_name, COUNT(*) as count
               FROM security_events
               WHERE author_name IS NOT NULL
               GROUP BY author_name
               ORDER BY count DESC
               LIMIT 5"""
        )
        top_authors = cur.fetchall()

        cur.execute(
            """SELECT tool_name, COUNT(*) as count
               FROM tool_calls
               WHERE tool_name IS NOT NULL
               GROUP BY tool_name
               ORDER BY count DESC"""
        )
        tool_breakdown = cur.fetchall()

        cur.execute(
            """SELECT
                COUNT(*) as total_oddities,
                SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) as critical_oddities
            FROM behavior_oddities"""
        )
        oddity_stats = cur.fetchone()

    return SecurityStatsOut(
        total_events=event_stats["total_events"] or 0,
        injection_attempts=event_stats["injection_attempts"] or 0,
        unauthorized_access=event_stats["unauthorized_access"] or 0,
        suspicious_patterns=event_stats["suspicious_patterns"] or 0,
        avg_risk_score=event_stats["avg_risk_score"],
        max_risk_score=event_stats["max_risk_score"],
        top_flagged_authors=[
            {"author": row["author_name"], "count": row["count"]}
            for row in top_authors
        ],
        tool_call_breakdown=[
            {"tool": row["tool_name"], "count": row["count"]}
            for row in tool_breakdown
        ],
        total_oddities=oddity_stats["total_oddities"] or 0,
        critical_oddities=oddity_stats["critical_oddities"] or 0,
    )


@router.get("/timeline", response_model=list[dict])
def get_security_timeline(
    days: int = Query(30, ge=1, le=365),
):
    """Get daily security event counts for timeline charting."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT
                date(timestamp::timestamp) as date,
                SUM(CASE WHEN event_type = 'injection_attempt' THEN 1 ELSE 0 END) as injections,
                SUM(CASE WHEN event_type = 'unauthorized_access' THEN 1 ELSE 0 END) as auth_failures,
                SUM(CASE WHEN event_type = 'suspicious_pattern' THEN 1 ELSE 0 END) as suspicious,
                COUNT(*) as total
            FROM security_events
            WHERE timestamp >= (CURRENT_DATE - make_interval(days => %s))::text
            GROUP BY date(timestamp::timestamp)
            ORDER BY date(timestamp::timestamp)""",
            (days,),
        )
        rows = cur.fetchall()

    return [
        {
            "date": str(row["date"]),
            "injections": row["injections"],
            "auth_failures": row["auth_failures"],
            "suspicious": row["suspicious"],
            "total": row["total"],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Blocked authors endpoints
# ---------------------------------------------------------------------------


def _row_to_blocked_author(row: dict) -> BlockedAuthorOut:
    """Convert a database row to a BlockedAuthorOut model."""
    return BlockedAuthorOut(
        **{
            k: str(v) if k in ("created_at", "blocked_at", "unblocked_at") and v is not None else v
            for k, v in row.items()
        }
    )


@router.get("/blocked-authors", response_model=PaginatedBlockedAuthors)
def list_blocked_authors(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    active_only: bool = Query(True),
):
    """List blocked authors with pagination."""
    conditions = []
    params: list = []

    if active_only:
        conditions.append("is_active = TRUE")

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) as total FROM blocked_authors {where}", params
        )
        total = cur.fetchone()["total"]

        offset = (page - 1) * per_page
        cur.execute(
            f"""SELECT * FROM blocked_authors {where}
                ORDER BY blocked_at DESC LIMIT %s OFFSET %s""",
            [*params, per_page, offset],
        )
        rows = cur.fetchall()

    return PaginatedBlockedAuthors(
        authors=[_row_to_blocked_author(row) for row in rows],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=max(1, math.ceil(total / per_page)),
    )


@router.post("/blocked-authors", response_model=BlockedAuthorOut, status_code=201)
def block_author(body: BlockAuthorIn):
    """Manually add an author to the blocklist."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO blocked_authors (author_name, reason, flag_count, is_active)
               VALUES (%s, %s, 0, TRUE)
               ON CONFLICT (author_name)
               DO UPDATE SET is_active = TRUE, blocked_at = NOW(),
                            reason = EXCLUDED.reason, unblocked_at = NULL
               RETURNING *""",
            (body.author_name, body.reason or "Manually blocked"),
        )
        row = cur.fetchone()
        conn.commit()

    return _row_to_blocked_author(row)


@router.post("/blocked-authors/unblock", response_model=BlockedAuthorOut)
def unblock_author_endpoint(body: UnblockAuthorIn):
    """Remove an author from the blocklist."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE blocked_authors
               SET is_active = FALSE, unblocked_at = NOW()
               WHERE author_name = %s AND is_active = TRUE
               RETURNING *""",
            (body.author_name,),
        )
        row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Author '{body.author_name}' is not currently blocked",
        )

    return _row_to_blocked_author(row)
