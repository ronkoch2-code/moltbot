import { useState, useEffect } from 'react';
import type { Prompt, PaginatedPrompts } from '@/types';
import { fetchPrompts, fetchActivePrompt, createPrompt } from '@/api/client';

export default function PromptsPage() {
  const [promptsData, setPromptsData] = useState<PaginatedPrompts | null>(null);
  const [activePrompt, setActivePrompt] = useState<Prompt | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formText, setFormText] = useState('');
  const [formSummary, setFormSummary] = useState('');
  const [formAuthor, setFormAuthor] = useState('CelticXfer');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const prompts = await fetchPrompts();
      setPromptsData(prompts);
      try {
        const active = await fetchActivePrompt();
        setActivePrompt(active);
      } catch {
        setActivePrompt(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load prompts');
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!formText.trim()) return;
    try {
      setSubmitting(true);
      await createPrompt({
        prompt_text: formText,
        change_summary: formSummary || undefined,
        author: formAuthor || 'system',
      });
      setShowForm(false);
      setFormText('');
      setFormSummary('');
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create prompt');
    } finally {
      setSubmitting(false);
    }
  }

  function handleNewVersion() {
    setFormText(activePrompt?.prompt_text || '');
    setFormSummary('');
    setShowForm(true);
  }

  if (loading && !promptsData) {
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
          onClick={loadData}
          className="mt-4 px-4 py-2 bg-red-800 rounded hover:bg-red-700 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Heartbeat Prompts</h1>
        <button
          onClick={handleNewVersion}
          className="px-4 py-2 bg-emerald-700 text-white rounded hover:bg-emerald-600 transition-colors"
        >
          New Version
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <form onSubmit={handleCreate} className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-white mb-4">Create New Prompt Version</h2>
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-1">Prompt Text</label>
            <textarea
              value={formText}
              onChange={(e) => setFormText(e.target.value)}
              rows={16}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-gray-100 font-mono text-sm focus:outline-none focus:border-emerald-600"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Change Summary</label>
              <input
                type="text"
                value={formSummary}
                onChange={(e) => setFormSummary(e.target.value)}
                placeholder="What changed?"
                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-emerald-600"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Author</label>
              <input
                type="text"
                value={formAuthor}
                onChange={(e) => setFormAuthor(e.target.value)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-emerald-600"
              />
            </div>
          </div>
          <div className="flex gap-3">
            <button
              type="submit"
              disabled={submitting || !formText.trim()}
              className="px-4 py-2 bg-emerald-700 text-white rounded hover:bg-emerald-600 transition-colors disabled:opacity-50"
            >
              {submitting ? 'Creating...' : 'Create Version'}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="px-4 py-2 bg-zinc-700 text-gray-300 rounded hover:bg-zinc-600 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Active prompt card */}
      {activePrompt && (
        <div className="bg-zinc-900 border border-emerald-800 rounded-lg p-6 mb-6">
          <div className="flex items-center gap-3 mb-3">
            <span className="text-xs font-medium bg-emerald-900 text-emerald-300 px-2 py-0.5 rounded">
              ACTIVE
            </span>
            <span className="text-sm text-gray-400">
              v{activePrompt.version} by {activePrompt.author}
            </span>
            <span className="text-sm text-gray-500">
              {new Date(activePrompt.created_at).toLocaleString()}
            </span>
          </div>
          {activePrompt.change_summary && (
            <p className="text-sm text-gray-400 mb-3 italic">{activePrompt.change_summary}</p>
          )}
          <pre className="bg-zinc-950 border border-zinc-800 rounded p-4 text-sm text-gray-300 font-mono whitespace-pre-wrap overflow-x-auto max-h-96 overflow-y-auto">
            {activePrompt.prompt_text}
          </pre>
        </div>
      )}

      {/* Version history */}
      <h2 className="text-lg font-semibold text-white mb-3">Version History</h2>
      {promptsData && promptsData.prompts.length === 0 ? (
        <div className="text-gray-500 text-center py-8">
          No prompts yet. Create the first version to get started.
        </div>
      ) : (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-gray-400 text-left">
                <th className="px-4 py-3 font-medium">Version</th>
                <th className="px-4 py-3 font-medium">Author</th>
                <th className="px-4 py-3 font-medium">Change Summary</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {promptsData?.prompts.map((prompt) => (
                <tr key={prompt.id} className="border-b border-zinc-800 hover:bg-zinc-800/50">
                  <td className="px-4 py-3 text-gray-100 font-mono">v{prompt.version}</td>
                  <td className="px-4 py-3 text-gray-300">{prompt.author}</td>
                  <td className="px-4 py-3 text-gray-400">{prompt.change_summary || '-'}</td>
                  <td className="px-4 py-3 text-gray-400">
                    {new Date(prompt.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    {prompt.is_active ? (
                      <span className="text-xs font-medium bg-emerald-900 text-emerald-300 px-2 py-0.5 rounded">
                        ACTIVE
                      </span>
                    ) : (
                      <span className="text-xs text-gray-500">inactive</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
