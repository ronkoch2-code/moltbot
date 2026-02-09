"""API routes for dashboard statistics."""

from fastapi import APIRouter, Query

from dashboard.api.database import get_db
from dashboard.api.models import StatsOut, TimelinePoint

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
def get_stats():
    """Get aggregate dashboard statistics."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COUNT(*) as total_runs,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful_runs,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
                AVG(duration_seconds) as avg_duration_seconds,
                MAX(started_at) as last_run_at
            FROM heartbeat_runs
            """
        )
        run_stats = cur.fetchone()

        cur.execute(
            """
            SELECT
                COUNT(*) as total_actions,
                SUM(CASE WHEN action_type = 'upvoted' THEN 1 ELSE 0 END) as total_upvotes,
                SUM(CASE WHEN action_type = 'commented' THEN 1 ELSE 0 END) as total_comments,
                SUM(CASE WHEN action_type = 'posted' THEN 1 ELSE 0 END) as total_posts,
                SUM(CASE WHEN action_type = 'subscribed' THEN 1 ELSE 0 END) as total_subscriptions
            FROM heartbeat_actions
            """
        )
        action_stats = cur.fetchone()

    return StatsOut(
        total_runs=run_stats["total_runs"] or 0,
        successful_runs=run_stats["successful_runs"] or 0,
        failed_runs=run_stats["failed_runs"] or 0,
        total_actions=action_stats["total_actions"] or 0,
        total_upvotes=action_stats["total_upvotes"] or 0,
        total_comments=action_stats["total_comments"] or 0,
        total_posts=action_stats["total_posts"] or 0,
        total_subscriptions=action_stats["total_subscriptions"] or 0,
        avg_duration_seconds=run_stats["avg_duration_seconds"],
        last_run_at=run_stats["last_run_at"],
    )


@router.get("/timeline", response_model=list[TimelinePoint])
def get_timeline(
    days: int = Query(30, ge=1, le=365),
):
    """Get daily counts for timeline charting."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                date(r.started_at::timestamp) as date,
                COUNT(DISTINCT r.run_id) as runs,
                COALESCE(SUM(a_stats.total_actions), 0) as actions,
                COALESCE(SUM(a_stats.upvotes), 0) as upvotes,
                COALESCE(SUM(a_stats.comments), 0) as comments,
                COALESCE(SUM(a_stats.posts), 0) as posts
            FROM heartbeat_runs r
            LEFT JOIN (
                SELECT
                    a.run_id,
                    COUNT(*) as total_actions,
                    SUM(CASE WHEN a.action_type = 'upvoted' THEN 1 ELSE 0 END) as upvotes,
                    SUM(CASE WHEN a.action_type = 'commented' THEN 1 ELSE 0 END) as comments,
                    SUM(CASE WHEN a.action_type = 'posted' THEN 1 ELSE 0 END) as posts
                FROM heartbeat_actions a
                GROUP BY a.run_id
            ) a_stats ON a_stats.run_id = r.run_id
            WHERE r.started_at >= (CURRENT_DATE - make_interval(days => %s))::text
            GROUP BY date(r.started_at::timestamp)
            ORDER BY date(r.started_at::timestamp)
            """,
            (days,),
        )
        rows = cur.fetchall()

    return [
        TimelinePoint(
            date=str(row["date"]),
            runs=row["runs"],
            actions=row["actions"],
            upvotes=row["upvotes"],
            comments=row["comments"],
            posts=row["posts"],
        )
        for row in rows
    ]
