export default function NotImplemented({ title, step }: { title: string; step: number }) {
  return (
    <section aria-labelledby="t">
      <h1 id="t" className="text-xl font-semibold">
        {title}
      </h1>
      <p className="mt-3 rounded border border-amber-700/60 bg-amber-950/40 p-3 text-sm text-amber-200">
        Not implemented yet — planned for build step {String(step).padStart(2, '0')}. Nothing on this
        screen is real data.
      </p>
    </section>
  )
}
