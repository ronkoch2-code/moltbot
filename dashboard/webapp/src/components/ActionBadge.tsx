interface ActionBadgeProps {
  actionType: 'upvoted' | 'commented' | 'posted' | 'subscribed' | 'welcomed' | 'browsed' | 'checked_status' | 'checked_submolts';
}

export default function ActionBadge({ actionType }: ActionBadgeProps) {
  const colors: Record<string, string> = {
    upvoted: 'bg-blue-900 text-blue-200 border-blue-700',
    commented: 'bg-green-900 text-green-200 border-green-700',
    posted: 'bg-purple-900 text-purple-200 border-purple-700',
    subscribed: 'bg-yellow-900 text-yellow-200 border-yellow-700',
    welcomed: 'bg-pink-900 text-pink-200 border-pink-700',
    browsed: 'bg-gray-800 text-gray-300 border-gray-700',
    checked_status: 'bg-slate-800 text-slate-300 border-slate-700',
    checked_submolts: 'bg-slate-800 text-slate-300 border-slate-700',
  };

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium border ${colors[actionType] || 'bg-gray-800 text-gray-300 border-gray-700'}`}>
      {actionType}
    </span>
  );
}
