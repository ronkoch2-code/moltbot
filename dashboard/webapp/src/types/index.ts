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
