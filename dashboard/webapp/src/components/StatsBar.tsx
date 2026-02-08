import type { Stats } from '@/types';

interface StatsBarProps {
  stats: Stats;
}

export default function StatsBar({ stats }: StatsBarProps) {
  const successRate = stats.total_runs > 0
    ? ((stats.successful_runs / stats.total_runs) * 100).toFixed(1)
    : '0.0';

  const lastRunDate = stats.last_run_at
    ? new Date(stats.last_run_at).toLocaleString()
    : 'Never';

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-4 mb-8">
      <div className="bg-blue-950 border border-blue-900 rounded-lg p-4">
        <div className="text-sm text-blue-300 mb-1">Total Runs</div>
        <div className="text-2xl font-bold text-white">{stats.total_runs}</div>
      </div>

      <div className="bg-green-950 border border-green-900 rounded-lg p-4">
        <div className="text-sm text-green-300 mb-1">Success Rate</div>
        <div className="text-2xl font-bold text-white">{successRate}%</div>
      </div>

      <div className="bg-purple-950 border border-purple-900 rounded-lg p-4">
        <div className="text-sm text-purple-300 mb-1">Actions</div>
        <div className="text-2xl font-bold text-white">{stats.total_actions}</div>
      </div>

      <div className="bg-indigo-950 border border-indigo-900 rounded-lg p-4">
        <div className="text-sm text-indigo-300 mb-1">Upvotes</div>
        <div className="text-2xl font-bold text-white">{stats.total_upvotes}</div>
      </div>

      <div className="bg-emerald-950 border border-emerald-900 rounded-lg p-4">
        <div className="text-sm text-emerald-300 mb-1">Comments</div>
        <div className="text-2xl font-bold text-white">{stats.total_comments}</div>
      </div>

      <div className="bg-violet-950 border border-violet-900 rounded-lg p-4">
        <div className="text-sm text-violet-300 mb-1">Posts</div>
        <div className="text-2xl font-bold text-white">{stats.total_posts}</div>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
        <div className="text-sm text-gray-400 mb-1">Last Run</div>
        <div className="text-sm font-semibold text-white truncate" title={lastRunDate}>
          {lastRunDate}
        </div>
      </div>
    </div>
  );
}
