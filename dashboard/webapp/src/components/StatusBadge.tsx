interface StatusBadgeProps {
  status: 'completed' | 'failed' | 'running';
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const colors = {
    completed: 'bg-green-900 text-green-200 border-green-700',
    failed: 'bg-red-900 text-red-200 border-red-700',
    running: 'bg-yellow-900 text-yellow-200 border-yellow-700',
  };

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium border ${colors[status]}`}>
      {status}
    </span>
  );
}
