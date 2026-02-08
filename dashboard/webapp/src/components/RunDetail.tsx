import { useState } from 'react';
import type { RunDetail as RunDetailType } from '@/types';
import StatusBadge from './StatusBadge';
import ActionBadge from './ActionBadge';

interface RunDetailProps {
  run: RunDetailType;
}

export default function RunDetail({ run }: RunDetailProps) {
  const [showRawOutput, setShowRawOutput] = useState(false);

  return (
    <div className="space-y-6">
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold text-white">Run #{run.run_number ?? '?'}</h2>
          <StatusBadge status={run.status} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-400">Agent:</span>
            <span className="ml-2 text-white font-medium">{run.agent_name}</span>
          </div>
          <div>
            <span className="text-gray-400">Script:</span>
            <span className="ml-2 text-white">{run.script_variant ?? 'unknown'}</span>
          </div>
          <div>
            <span className="text-gray-400">Started:</span>
            <span className="ml-2 text-white">{new Date(run.started_at).toLocaleString()}</span>
          </div>
          {run.finished_at && (
            <div>
              <span className="text-gray-400">Finished:</span>
              <span className="ml-2 text-white">{new Date(run.finished_at).toLocaleString()}</span>
            </div>
          )}
          {run.duration_seconds !== null && (
            <div>
              <span className="text-gray-400">Duration:</span>
              <span className="ml-2 text-white">{run.duration_seconds.toFixed(1)}s</span>
            </div>
          )}
          {run.exit_code !== null && (
            <div>
              <span className="text-gray-400">Exit Code:</span>
              <span className={`ml-2 ${run.exit_code === 0 ? 'text-green-400' : 'text-red-400'}`}>
                {run.exit_code}
              </span>
            </div>
          )}
        </div>

        {run.summary && (
          <div className="mt-4">
            <div className="text-gray-400 text-sm mb-1">Summary</div>
            <p className="text-white">{run.summary}</p>
          </div>
        )}

        {run.error_message && (
          <div className="mt-4">
            <div className="text-red-400 text-sm mb-1">Error</div>
            <p className="text-red-300 bg-red-950 border border-red-900 rounded p-3">
              {run.error_message}
            </p>
          </div>
        )}
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
        <h3 className="text-xl font-bold text-white mb-4">
          Actions ({run.actions.length})
        </h3>

        {run.actions.length === 0 ? (
          <p className="text-gray-400 text-center py-4">No actions recorded</p>
        ) : (
          <div className="space-y-3">
            {run.actions.map((action) => (
              <div key={action.id} className="bg-zinc-800 border border-zinc-700 rounded p-3">
                <div className="flex items-center justify-between mb-1">
                  <ActionBadge actionType={action.action_type} />
                  {!action.succeeded && (
                    <span className="text-xs text-red-400">Failed</span>
                  )}
                </div>

                <div className="text-sm text-gray-300 mt-1">
                  {action.target_author && (
                    <span className="text-blue-400">{action.target_author}</span>
                  )}
                  {action.target_author && action.detail && (
                    <span className="text-gray-500"> &mdash; </span>
                  )}
                  {action.detail && (
                    <span>{action.detail}</span>
                  )}
                  {action.target_title && (
                    <span className="text-gray-400 ml-2">&ldquo;{action.target_title}&rdquo;</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {run.raw_output && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
          <button
            onClick={() => setShowRawOutput(!showRawOutput)}
            className="flex items-center justify-between w-full text-left"
          >
            <h3 className="text-xl font-bold text-white">Raw Output</h3>
            <span className="text-gray-400 text-xl">{showRawOutput ? '-' : '+'}</span>
          </button>

          {showRawOutput && (
            <pre className="mt-4 p-4 bg-zinc-950 border border-zinc-800 rounded overflow-x-auto text-sm text-gray-300 whitespace-pre-wrap">
              {run.raw_output}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
