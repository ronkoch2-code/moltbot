import { useNavigate } from 'react-router-dom';
import type { Run } from '@/types';
import StatusBadge from './StatusBadge';

interface RunTimelineProps {
  runs: Run[];
}

export default function RunTimeline({ runs }: RunTimelineProps) {
  const navigate = useNavigate();

  if (runs.length === 0) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-8 text-center text-gray-400">
        No runs found
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {runs.map((run) => (
        <div
          key={run.id}
          onClick={() => navigate(`/runs/${run.run_id}`)}
          className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 hover:border-zinc-700 cursor-pointer transition-colors"
        >
          <div className="flex items-start justify-between mb-2">
            <div className="flex items-center gap-3">
              <StatusBadge status={run.status} />
              <span className="text-sm text-gray-400">
                {new Date(run.started_at).toLocaleString()}
              </span>
            </div>
            <div className="text-sm text-gray-400">
              Run #{run.run_number}
            </div>
          </div>

          <div className="mb-2">
            <span className="font-semibold text-white">{run.agent_name}</span>
          </div>

          {run.summary && (
            <p className="text-gray-400 text-sm mb-2 line-clamp-2">
              {run.summary}
            </p>
          )}

          {run.error_message && (
            <p className="text-red-400 text-sm mb-2 line-clamp-1">
              Error: {run.error_message}
            </p>
          )}

          <div className="flex items-center gap-4 text-xs text-gray-500">
            <span>{run.action_count} actions</span>
            {run.duration_seconds !== null && (
              <span>{run.duration_seconds.toFixed(1)}s</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
