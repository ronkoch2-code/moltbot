"""Pydantic models for heartbeat activity dashboard API."""

from pydantic import BaseModel, Field


class ActionOut(BaseModel):
    """A single action taken during a heartbeat run."""

    id: int
    run_id: str
    action_type: str
    target_id: str | None = None
    target_title: str | None = None
    target_author: str | None = None
    detail: str | None = None
    succeeded: bool = True
    created_at: str


class RunOut(BaseModel):
    """A heartbeat run summary."""

    id: int
    run_id: str
    started_at: str
    finished_at: str | None = None
    duration_seconds: float | None = None
    exit_code: int | None = None
    status: str
    agent_name: str
    script_variant: str | None = None
    run_number: int | None = None
    summary: str | None = None
    error_message: str | None = None
    action_count: int = 0
    created_at: str


class RunDetailOut(RunOut):
    """A heartbeat run with full details including actions and raw output."""

    raw_output: str | None = None
    actions: list[ActionOut] = Field(default_factory=list)


class PaginatedRuns(BaseModel):
    """Paginated list of runs."""

    runs: list[RunOut]
    total: int
    page: int
    per_page: int
    total_pages: int


class PaginatedActions(BaseModel):
    """Paginated list of actions."""

    actions: list[ActionOut]
    total: int
    page: int
    per_page: int
    total_pages: int


class StatsOut(BaseModel):
    """Aggregate dashboard statistics."""

    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    total_actions: int = 0
    total_upvotes: int = 0
    total_comments: int = 0
    total_posts: int = 0
    total_subscriptions: int = 0
    avg_duration_seconds: float | None = None
    last_run_at: str | None = None


class TimelinePoint(BaseModel):
    """A single point on the stats timeline."""

    date: str
    runs: int = 0
    actions: int = 0
    upvotes: int = 0
    comments: int = 0
    posts: int = 0


class RunCreateIn(BaseModel):
    """Input for creating a new run."""

    run_id: str
    started_at: str
    agent_name: str
    script_variant: str | None = None
    run_number: int | None = None
    raw_output: str | None = None


class RunUpdateIn(BaseModel):
    """Input for updating a run."""

    finished_at: str | None = None
    duration_seconds: float | None = None
    exit_code: int | None = None
    status: str | None = None
    summary: str | None = None
    error_message: str | None = None
    raw_output: str | None = None


class ActionCreateIn(BaseModel):
    """Input for recording an action."""

    action_type: str
    target_id: str | None = None
    target_title: str | None = None
    target_author: str | None = None
    detail: str | None = None
    succeeded: bool = True


class HealthOut(BaseModel):
    """Health check response."""

    status: str = "ok"
    database: str = "ok"
