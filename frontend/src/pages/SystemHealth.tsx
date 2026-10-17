import { useQuery } from '@tanstack/react-query'
import { getLive, getReady } from '../api/client'

export default function SystemHealth() {
  const live = useQuery({ queryKey: ['health', 'live'], queryFn: getLive, refetchInterval: 5000 })
  const ready = useQuery({ queryKey: ['health', 'ready'], queryFn: getReady, refetchInterval: 5000 })
  return (
    <section aria-labelledby="t">
      <h1 id="t" className="text-xl font-semibold">
        System Health
      </h1>
      <dl className="mt-4 grid max-w-xl grid-cols-[10rem_1fr] gap-y-2 text-sm">
        <dt className="text-slate-400">API liveness</dt>
        <dd>{live.isError ? 'unreachable' : (live.data?.status ?? '…')}</dd>
        <dt className="text-slate-400">Overall readiness</dt>
        <dd>{ready.isError ? 'unreachable' : (ready.data?.status ?? '…')}</dd>
        {ready.data &&
          Object.entries(ready.data.components).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-slate-400 capitalize">{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
      </dl>
      {ready.data?.detail && <p className="mt-4 text-sm text-slate-400">{ready.data.detail}</p>}
    </section>
  )
}
