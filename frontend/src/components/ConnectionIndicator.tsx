import { useQuery } from '@tanstack/react-query'
import { getLive } from '../api/client'

export default function ConnectionIndicator() {
  const { data, isError, isLoading, dataUpdatedAt } = useQuery({
    queryKey: ['health', 'live'],
    queryFn: getLive,
    refetchInterval: 5000,
  })
  const state = isLoading ? 'checking' : isError ? 'down' : data?.status === 'alive' ? 'up' : 'down'
  const styles = {
    checking: 'bg-slate-500',
    up: 'bg-emerald-500',
    down: 'bg-red-500',
  } as const
  const label = {
    checking: 'Checking API…',
    up: 'API reachable',
    down: 'API unreachable',
  }[state]
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-2 text-sm">
      <span aria-hidden className={`h-2.5 w-2.5 rounded-full ${styles[state]}`} />
      <span>{label}</span>
      {state === 'up' && (
        <span className="text-slate-400">· checked {new Date(dataUpdatedAt).toLocaleTimeString()}</span>
      )}
    </div>
  )
}
