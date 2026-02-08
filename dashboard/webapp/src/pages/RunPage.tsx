import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import type { RunDetail as RunDetailType } from '@/types';
import { fetchRun } from '@/api/client';
import RunDetail from '@/components/RunDetail';

export default function RunPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [run, setRun] = useState<RunDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (runId) {
      loadRun(runId);
    }
  }, [runId]);

  async function loadRun(id: string) {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchRun(id);
      setRun(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load run details');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="text-gray-400">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <button
          onClick={() => navigate('/')}
          className="mb-4 text-blue-400 hover:text-blue-300 transition-colors"
        >
          ← Back to Dashboard
        </button>
        <div className="bg-red-950 border border-red-900 rounded-lg p-6 text-red-200">
          <h2 className="text-xl font-bold mb-2">Error</h2>
          <p>{error}</p>
          <button
            onClick={() => runId && loadRun(runId)}
            className="mt-4 px-4 py-2 bg-red-800 rounded hover:bg-red-700 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!run) {
    return (
      <div>
        <button
          onClick={() => navigate('/')}
          className="mb-4 text-blue-400 hover:text-blue-300 transition-colors"
        >
          ← Back to Dashboard
        </button>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-8 text-center text-gray-400">
          Run not found
        </div>
      </div>
    );
  }

  return (
    <div>
      <button
        onClick={() => navigate('/')}
        className="mb-6 text-blue-400 hover:text-blue-300 transition-colors"
      >
        ← Back to Dashboard
      </button>
      <RunDetail run={run} />
    </div>
  );
}
