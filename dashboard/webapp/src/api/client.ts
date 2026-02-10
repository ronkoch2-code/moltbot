import type { Stats, TimelinePoint, PaginatedRuns, RunDetail, PaginatedActions, RunFilters, PaginatedPrompts, Prompt, PaginatedSecurityEvents, PaginatedToolCalls, PaginatedOddities, SecurityStats, SecurityTimelinePoint } from '@/types';

const API_BASE = '/api';
const AUTH_TOKEN = import.meta.env.VITE_DASHBOARD_AUTH_TOKEN || '';

function authHeaders(): HeadersInit {
  const headers: Record<string, string> = {};
  if (AUTH_TOKEN) {
    headers['Authorization'] = `Bearer ${AUTH_TOKEN}`;
  }
  return headers;
}

async function fetchJSON<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: authHeaders() });
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function fetchStats(): Promise<Stats> {
  return fetchJSON<Stats>(`${API_BASE}/stats`);
}

export async function fetchTimeline(days: number = 30): Promise<TimelinePoint[]> {
  return fetchJSON<TimelinePoint[]>(`${API_BASE}/stats/timeline?days=${days}`);
}

export async function fetchRuns(filters: RunFilters = {}): Promise<PaginatedRuns> {
  const params = new URLSearchParams();

  if (filters.page) params.append('page', filters.page.toString());
  if (filters.per_page) params.append('per_page', filters.per_page.toString());
  if (filters.status) params.append('status', filters.status);
  if (filters.agent_name) params.append('agent_name', filters.agent_name);
  if (filters.search) params.append('search', filters.search);
  if (filters.date_from) params.append('date_from', filters.date_from);
  if (filters.date_to) params.append('date_to', filters.date_to);

  const queryString = params.toString();
  const url = queryString ? `${API_BASE}/runs?${queryString}` : `${API_BASE}/runs`;

  return fetchJSON<PaginatedRuns>(url);
}

export async function fetchRun(runId: string): Promise<RunDetail> {
  return fetchJSON<RunDetail>(`${API_BASE}/runs/${runId}`);
}

export async function fetchActions(filters: {
  page?: number;
  per_page?: number;
  action_type?: string;
  date_from?: string;
  date_to?: string;
} = {}): Promise<PaginatedActions> {
  const params = new URLSearchParams();

  if (filters.page) params.append('page', filters.page.toString());
  if (filters.per_page) params.append('per_page', filters.per_page.toString());
  if (filters.action_type) params.append('action_type', filters.action_type);
  if (filters.date_from) params.append('date_from', filters.date_from);
  if (filters.date_to) params.append('date_to', filters.date_to);

  const queryString = params.toString();
  const url = queryString ? `${API_BASE}/actions?${queryString}` : `${API_BASE}/actions`;

  return fetchJSON<PaginatedActions>(url);
}

export async function fetchPrompts(page: number = 1, perPage: number = 20): Promise<PaginatedPrompts> {
  return fetchJSON<PaginatedPrompts>(`${API_BASE}/prompts?page=${page}&per_page=${perPage}`);
}

export async function fetchActivePrompt(): Promise<Prompt> {
  return fetchJSON<Prompt>(`${API_BASE}/prompts/active`);
}

export async function createPrompt(body: {
  prompt_text: string;
  change_summary?: string;
  author?: string;
}): Promise<Prompt> {
  return postJSON<Prompt>(`${API_BASE}/prompts`, body);
}

export async function fetchSecurityEvents(filters: {
  page?: number;
  per_page?: number;
  event_type?: string;
  date_from?: string;
  date_to?: string;
  min_risk_score?: number;
} = {}): Promise<PaginatedSecurityEvents> {
  const params = new URLSearchParams();
  if (filters.page) params.append('page', filters.page.toString());
  if (filters.per_page) params.append('per_page', filters.per_page.toString());
  if (filters.event_type) params.append('event_type', filters.event_type);
  if (filters.date_from) params.append('date_from', filters.date_from);
  if (filters.date_to) params.append('date_to', filters.date_to);
  if (filters.min_risk_score !== undefined) params.append('min_risk_score', filters.min_risk_score.toString());
  const qs = params.toString();
  return fetchJSON<PaginatedSecurityEvents>(qs ? `${API_BASE}/security/events?${qs}` : `${API_BASE}/security/events`);
}

export async function fetchSecurityStats(): Promise<SecurityStats> {
  return fetchJSON<SecurityStats>(`${API_BASE}/security/stats`);
}

export async function fetchToolCalls(filters: {
  page?: number;
  per_page?: number;
  tool_name?: string;
  date_from?: string;
  date_to?: string;
} = {}): Promise<PaginatedToolCalls> {
  const params = new URLSearchParams();
  if (filters.page) params.append('page', filters.page.toString());
  if (filters.per_page) params.append('per_page', filters.per_page.toString());
  if (filters.tool_name) params.append('tool_name', filters.tool_name);
  if (filters.date_from) params.append('date_from', filters.date_from);
  if (filters.date_to) params.append('date_to', filters.date_to);
  const qs = params.toString();
  return fetchJSON<PaginatedToolCalls>(qs ? `${API_BASE}/security/tool-calls?${qs}` : `${API_BASE}/security/tool-calls`);
}

export async function fetchOddities(filters: {
  page?: number;
  per_page?: number;
  oddity_type?: string;
  severity?: string;
} = {}): Promise<PaginatedOddities> {
  const params = new URLSearchParams();
  if (filters.page) params.append('page', filters.page.toString());
  if (filters.per_page) params.append('per_page', filters.per_page.toString());
  if (filters.oddity_type) params.append('oddity_type', filters.oddity_type);
  if (filters.severity) params.append('severity', filters.severity);
  const qs = params.toString();
  return fetchJSON<PaginatedOddities>(qs ? `${API_BASE}/security/oddities?${qs}` : `${API_BASE}/security/oddities`);
}

export async function fetchSecurityTimeline(days: number = 30): Promise<SecurityTimelinePoint[]> {
  return fetchJSON<SecurityTimelinePoint[]>(`${API_BASE}/security/timeline?days=${days}`);
}
