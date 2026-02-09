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
    prompt_version_id: int | None = None
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


class PromptOut(BaseModel):
    """A heartbeat prompt version."""

    id: int
    version: int
    prompt_text: str
    change_summary: str | None = None
    author: str
    is_active: bool
    created_at: str


class PromptCreateIn(BaseModel):
    """Input for creating a new prompt version."""

    prompt_text: str
    change_summary: str | None = None
    author: str = "system"


class PaginatedPrompts(BaseModel):
    """Paginated list of prompt versions."""

    prompts: list[PromptOut]
    total: int
    page: int
    per_page: int
    total_pages: int


class SecurityEventOut(BaseModel):
    """A single security event."""

    id: int
    event_type: str
    timestamp: str
    source_ip: str | None = None
    post_id: str | None = None
    author_name: str | None = None
    submolt_name: str | None = None
    risk_score: float | None = None
    flags: str | None = None
    fields_affected: str | None = None
    target_path: str | None = None
    raw_log_line: str | None = None
    created_at: str


class PaginatedSecurityEvents(BaseModel):
    """Paginated list of security events."""

    events: list[SecurityEventOut]
    total: int
    page: int
    per_page: int
    total_pages: int


class ToolCallOut(BaseModel):
    """A single MCP tool call record."""

    id: int
    timestamp: str
    tool_name: str | None = None
    target_id: str | None = None
    target_type: str | None = None
    direction: str | None = None
    http_method: str | None = None
    http_url: str | None = None
    http_status: int | None = None
    raw_log_line: str | None = None
    created_at: str


class PaginatedToolCalls(BaseModel):
    """Paginated list of tool calls."""

    tool_calls: list[ToolCallOut]
    total: int
    page: int
    per_page: int
    total_pages: int


class OddityOut(BaseModel):
    """A single behavior oddity."""

    id: int
    oddity_type: str
    description: str
    severity: str
    related_tool_call_ids: str | None = None
    detected_at: str
    created_at: str


class PaginatedOddities(BaseModel):
    """Paginated list of behavior oddities."""

    oddities: list[OddityOut]
    total: int
    page: int
    per_page: int
    total_pages: int


class SecurityStatsOut(BaseModel):
    """Aggregate security statistics."""

    total_events: int = 0
    injection_attempts: int = 0
    unauthorized_access: int = 0
    suspicious_patterns: int = 0
    avg_risk_score: float | None = None
    max_risk_score: float | None = None
    top_flagged_authors: list[dict] = Field(default_factory=list)
    tool_call_breakdown: list[dict] = Field(default_factory=list)
    total_oddities: int = 0
    critical_oddities: int = 0


class HealthOut(BaseModel):
    """Health check response."""

    status: str = "ok"
    database: str = "ok"
