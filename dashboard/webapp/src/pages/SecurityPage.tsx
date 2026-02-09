import { useState, useEffect } from 'react';
import type { SecurityStats, PaginatedSecurityEvents, PaginatedToolCalls, PaginatedOddities } from '@/types';
import { fetchSecurityStats, fetchSecurityEvents, fetchToolCalls, fetchOddities } from '@/api/client';

type Tab = 'injections' | 'auth' | 'oddities' | 'tool_calls';

export default function SecurityPage() {
  const [stats, setStats] = useState<SecurityStats | null>(null);
  const [events, setEvents] = useState<PaginatedSecurityEvents | null>(null);
  const [toolCallsData, setToolCallsData] = useState<PaginatedToolCalls | null>(null);
  const [odditiesData, setOdditiesData] = useState<PaginatedOddities | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('injections');
  const [page, setPage] = useState(1);

  useEffect(() => {
    loadStats();
  }, []);

  useEffect(() => {
    setPage(1);
  }, [activeTab]);

  useEffect(() => {
    loadTabData();
  }, [activeTab, page]);

  async function loadStats() {
    try {
      const s = await fetchSecurityStats();
      setStats(s);
    } catch {
      // non-fatal
    }
  }

  async function loadTabData() {
    try {
      setLoading(true);
      setError(null);

      switch (activeTab) {
        case 'injections':
          setEvents(await fetchSecurityEvents({ page, per_page: 20, event_type: 'injection_attempt' }));
          break;
        case 'auth':
          setEvents(await fetchSecurityEvents({ page, per_page: 20, event_type: 'unauthorized_access' }));
          break;
        case 'oddities':
          setOdditiesData(await fetchOddities({ page, per_page: 20 }));
          break;
        case 'tool_calls':
          setToolCallsData(await fetchToolCalls({ page, per_page: 20 }));
          break;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'injections', label: 'Injections' },
    { key: 'auth', label: 'Auth' },
    { key: 'oddities', label: 'Oddities' },
    { key: 'tool_calls', label: 'Tool Calls' },
  ];

  const severityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'text-red-400 bg-red-950';
      case 'warning': return 'text-yellow-400 bg-yellow-950';
      default: return 'text-blue-400 bg-blue-950';
    }
  };

  const statusColor = (status: number | null) => {
    if (!status) return 'text-gray-400';
    if (status >= 500) return 'text-red-400';
    if (status >= 400) return 'text-yellow-400';
    return 'text-green-400';
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-6">Security Analytics</h1>

      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
          <StatCard label="Total Events" value={stats.total_events} />
          <StatCard label="Injection Attempts" value={stats.injection_attempts} color="text-red-400" />
          <StatCard label="Unauthorized Access" value={stats.unauthorized_access} color="text-yellow-400" />
          <StatCard label="Oddities" value={stats.total_oddities} color="text-orange-400" />
          <StatCard
            label="Max Risk Score"
            value={stats.max_risk_score !== null ? stats.max_risk_score.toFixed(3) : 'N/A'}
            color="text-purple-400"
          />
        </div>
      )}

      {/* Top flagged authors */}
      {stats && stats.top_flagged_authors.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 mb-6">
          <h3 className="text-sm font-semibold text-gray-400 mb-2">Top Flagged Authors</h3>
          <div className="flex flex-wrap gap-2">
            {stats.top_flagged_authors.map((a) => (
              <span key={a.author} className="px-2 py-1 bg-zinc-800 rounded text-sm text-gray-300">
                {a.author} ({a.count})
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-zinc-800 mb-6">
        <div className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 text-sm font-medium rounded-t transition-colors ${
                activeTab === tab.key
                  ? 'bg-zinc-800 text-white border-b-2 border-blue-500'
                  : 'text-gray-400 hover:text-white hover:bg-zinc-900'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="bg-red-950 border border-red-900 rounded-lg p-4 text-red-200 mb-4">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center min-h-48">
          <div className="text-gray-400">Loading...</div>
        </div>
      ) : (
        <>
          {/* Injections / Auth tab */}
          {(activeTab === 'injections' || activeTab === 'auth') && events && (
            <div>
              {events.events.length === 0 ? (
                <div className="text-gray-500 text-center py-8">No events found.</div>
              ) : (
                <div className="space-y-3">
                  {events.events.map((event) => (
                    <div key={event.id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-mono ${
                            event.event_type === 'injection_attempt' ? 'bg-red-950 text-red-400' : 'bg-yellow-950 text-yellow-400'
                          }`}>
                            {event.event_type}
                          </span>
                          {event.risk_score !== null && (
                            <span className="text-sm text-purple-400">
                              risk: {event.risk_score.toFixed(3)}
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-gray-500">{event.timestamp}</span>
                      </div>
                      <div className="text-sm text-gray-300 space-y-1">
                        {event.author_name && <div>Author: <span className="text-white">{event.author_name}</span></div>}
                        {event.submolt_name && <div>Submolt: <span className="text-white">{event.submolt_name}</span></div>}
                        {event.post_id && <div>Post: <span className="font-mono text-xs text-gray-400">{event.post_id}</span></div>}
                        {event.source_ip && <div>IP: <span className="font-mono text-gray-400">{event.source_ip}</span></div>}
                        {event.target_path && <div>Path: <span className="font-mono text-gray-400">{event.target_path}</span></div>}
                        {event.flags && (
                          <div className="mt-2">
                            <span className="text-gray-500">Flags: </span>
                            <span className="font-mono text-xs text-orange-300">{event.flags}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {events.total_pages > 1 && (
                <PageNav current={events.page} total={events.total_pages} onChange={setPage} />
              )}
            </div>
          )}

          {/* Oddities tab */}
          {activeTab === 'oddities' && odditiesData && (
            <div>
              {odditiesData.oddities.length === 0 ? (
                <div className="text-gray-500 text-center py-8">No oddities detected.</div>
              ) : (
                <div className="space-y-3">
                  {odditiesData.oddities.map((o) => (
                    <div key={o.id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-mono ${severityColor(o.severity)}`}>
                            {o.severity}
                          </span>
                          <span className="text-sm text-gray-300 font-mono">{o.oddity_type}</span>
                        </div>
                        <span className="text-xs text-gray-500">{o.detected_at}</span>
                      </div>
                      <p className="text-sm text-gray-300">{o.description}</p>
                    </div>
                  ))}
                </div>
              )}
              {odditiesData.total_pages > 1 && (
                <PageNav current={odditiesData.page} total={odditiesData.total_pages} onChange={setPage} />
              )}
            </div>
          )}

          {/* Tool Calls tab */}
          {activeTab === 'tool_calls' && toolCallsData && (
            <div>
              {/* Tool call breakdown from stats */}
              {stats && stats.tool_call_breakdown.length > 0 && (
                <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 mb-4">
                  <h3 className="text-sm font-semibold text-gray-400 mb-2">Tool Usage Breakdown</h3>
                  <div className="flex flex-wrap gap-2">
                    {stats.tool_call_breakdown.map((t) => (
                      <span key={t.tool} className="px-2 py-1 bg-zinc-800 rounded text-sm text-gray-300">
                        {t.tool} ({t.count})
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {toolCallsData.tool_calls.length === 0 ? (
                <div className="text-gray-500 text-center py-8">No tool calls recorded.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-gray-400 text-left border-b border-zinc-800">
                        <th className="py-2 px-3">Time</th>
                        <th className="py-2 px-3">Tool</th>
                        <th className="py-2 px-3">Target</th>
                        <th className="py-2 px-3">Method</th>
                        <th className="py-2 px-3">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {toolCallsData.tool_calls.map((tc) => (
                        <tr key={tc.id} className="border-b border-zinc-800/50 hover:bg-zinc-900">
                          <td className="py-2 px-3 text-gray-500 text-xs whitespace-nowrap">{tc.timestamp}</td>
                          <td className="py-2 px-3 text-gray-200 font-mono">{tc.tool_name || '-'}</td>
                          <td className="py-2 px-3 text-gray-400 font-mono text-xs">
                            {tc.target_id ? `${tc.target_type}:${tc.target_id.slice(0, 8)}` : '-'}
                            {tc.direction && <span className="ml-1 text-blue-400">({tc.direction})</span>}
                          </td>
                          <td className="py-2 px-3 text-gray-400">{tc.http_method || '-'}</td>
                          <td className={`py-2 px-3 font-mono ${statusColor(tc.http_status)}`}>
                            {tc.http_status || '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {toolCallsData.total_pages > 1 && (
                <PageNav current={toolCallsData.page} total={toolCallsData.total_pages} onChange={setPage} />
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StatCard({ label, value, color = 'text-white' }: { label: string; value: number | string; color?: string }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
    </div>
  );
}

function PageNav({ current, total, onChange }: { current: number; total: number; onChange: (p: number) => void }) {
  return (
    <div className="flex items-center justify-center gap-4 mt-6">
      <button
        disabled={current <= 1}
        onClick={() => onChange(current - 1)}
        className="px-3 py-1 bg-zinc-800 rounded text-sm disabled:opacity-40 hover:bg-zinc-700 transition-colors"
      >
        Prev
      </button>
      <span className="text-sm text-gray-400">
        Page {current} of {total}
      </span>
      <button
        disabled={current >= total}
        onClick={() => onChange(current + 1)}
        className="px-3 py-1 bg-zinc-800 rounded text-sm disabled:opacity-40 hover:bg-zinc-700 transition-colors"
      >
        Next
      </button>
    </div>
  );
}
