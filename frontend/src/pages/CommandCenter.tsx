import Header from '../components/Header'
import ScenePane from '../components/ScenePane'
import { useStore } from '../lib/store'
import { api } from '../lib/api'

export default function CommandCenter() {
  const snap = useStore((s) => s.snap)
  return (
    <div className="scanlines vignette flex h-full flex-col overflow-hidden">
      <div className="sweep" />
      <Header>
        <button className="btn" onClick={() => api.post('/api/scenario/reset')}>Reset scenario</button>
      </Header>
      <main className="relative flex min-h-0 flex-1">
        <aside className="z-10 flex w-[340px] shrink-0 flex-col gap-2 p-2" />
        <section className="relative min-w-0 flex-1"><ScenePane /></section>
        <aside className="z-10 flex w-[380px] shrink-0 flex-col gap-2 p-2" />
      </main>
      {!snap && <div className="absolute inset-0 grid place-items-center font-mono text-cyan/50">ESTABLISHING LINK…</div>}
    </div>
  )
}
