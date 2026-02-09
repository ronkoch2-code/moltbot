export interface Run {
  id: number;
  run_id: string;
  run_number: number | null;
  agent_name: string;
  script_variant: string | null;
  status: 'completed' | 'failed' | 'running';
  started_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  exit_code: number | null;
  summary: string | null;
  error_message: string | null;
  action_count: number;
  prompt_version_id: number | null;
  created_at: string;
}

export interface Action {
  id: number;
  run_id: string;
  action_type: 'upvoted' | 'commented' | 'posted' | 'subscribed' | 'welcomed' | 'browsed' | 'checked_status' | 'checked_submolts';
  target_id: string | null;
  target_title: string | null;
  target_author: string | null;
  detail: string | null;
  succeeded: boolean;
  created_at: string;
}

export interface RunDetail extends Run {
  actions: Action[];
  raw_output: string | null;
}

export interface PaginatedRuns {
  runs: Run[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface PaginatedActions {
  actions: Action[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface Stats {
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  total_actions: number;
  total_upvotes: number;
  total_comments: number;
  total_posts: number;
  total_subscriptions: number;
  avg_duration_seconds: number | null;
  last_run_at: string | null;
}

export interface TimelinePoint {
  date: string;
  runs: number;
  actions: number;
  upvotes: number;
  comments: number;
  posts: number;
}

export interface RunFilters {
  page?: number;
  per_page?: number;
  status?: string;
  agent_name?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
}

export interface Prompt {
  id: number;
  version: number;
  prompt_text: string;
  change_summary: string | null;
  author: string;
  is_active: boolean;
  created_at: string;
}

export interface PaginatedPrompts {
  prompts: Prompt[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface SecurityEvent {
  id: number;
  event_type: 'injection_attempt' | 'unauthorized_access' | 'suspicious_pattern';
  timestamp: string;
  source_ip: string | null;
  post_id: string | null;
  author_name: string | null;
  submolt_name: string | null;
  risk_score: number | null;
  flags: string | null;
  fields_affected: string | null;
  target_path: string | null;
  raw_log_line: string | null;
  created_at: string;
}

export interface PaginatedSecurityEvents {
  events: SecurityEvent[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface ToolCall {
  id: number;
  timestamp: string;
  tool_name: string | null;
  target_id: string | null;
  target_type: string | null;
  direction: string | null;
  http_method: string | null;
  http_url: string | null;
  http_status: number | null;
  raw_log_line: string | null;
  created_at: string;
}

export interface PaginatedToolCalls {
  tool_calls: ToolCall[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface Oddity {
  id: number;
  oddity_type: 'duplicate_vote' | 'failed_api_call' | 'excessive_calls';
  description: string;
  severity: 'info' | 'warning' | 'critical';
  related_tool_call_ids: string | null;
  detected_at: string;
  created_at: string;
}

export interface PaginatedOddities {
  oddities: Oddity[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface SecurityStats {
  total_events: number;
  injection_attempts: number;
  unauthorized_access: number;
  suspicious_patterns: number;
  avg_risk_score: number | null;
  max_risk_score: number | null;
  top_flagged_authors: { author: string; count: number }[];
  tool_call_breakdown: { tool: string; count: number }[];
  total_oddities: number;
  critical_oddities: number;
}

export interface SecurityTimelinePoint {
  date: string;
  injections: number;
  auth_failures: number;
  suspicious: number;
  total: number;
}
