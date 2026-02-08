import type { Stats, TimelinePoint, PaginatedRuns, RunDetail, PaginatedActions, RunFilters } from '@/types';

const API_BASE = '/api';

async function fetchJSON<T>(url: string): Promise<T> {
  const response = await fetch(url);
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
