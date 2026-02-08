import { useState, useEffect } from 'react';
import type { Stats, PaginatedRuns, RunFilters } from '@/types';
import { fetchStats, fetchRuns } from '@/api/client';
import StatsBar from '@/components/StatsBar';
import SearchFilter from '@/components/SearchFilter';
import RunTimeline from '@/components/RunTimeline';
import Pagination from '@/components/Pagination';

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [runsData, setRunsData] = useState<PaginatedRuns | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<RunFilters>({ page: 1, per_page: 20 });

  useEffect(() => {
    loadDashboardData();
  }, [filters]);

  async function loadDashboardData() {
    try {
      setLoading(true);
      setError(null);

      const [statsResponse, runsResponse] = await Promise.all([
        fetchStats(),
        fetchRuns(filters),
      ]);

      setStats(statsResponse);
      setRunsData(runsResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  }

  const handleFilterChange = (newFilters: RunFilters) => {
    setFilters({ ...filters, ...newFilters });
  };

  const handlePageChange = (page: number) => {
    setFilters({ ...filters, page });
  };

  if (loading && !stats) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="text-gray-400">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-950 border border-red-900 rounded-lg p-6 text-red-200">
        <h2 className="text-xl font-bold mb-2">Error</h2>
        <p>{error}</p>
        <button
          onClick={loadDashboardData}
          className="mt-4 px-4 py-2 bg-red-800 rounded hover:bg-red-700 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      {stats && <StatsBar stats={stats} />}

      <SearchFilter onFilterChange={handleFilterChange} />

      {runsData && (
        <>
          <RunTimeline runs={runsData.runs} />
          {runsData.total_pages > 1 && (
            <Pagination
              currentPage={runsData.page}
              totalPages={runsData.total_pages}
              onPageChange={handlePageChange}
            />
          )}
        </>
      )}

      {loading && runsData && (
        <div className="text-center text-gray-400 mt-4">Loading...</div>
      )}
    </div>
  );
}
