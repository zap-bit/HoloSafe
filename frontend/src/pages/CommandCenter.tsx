import Header from '../components/Header'
import ScenePane from '../components/ScenePane'
import { useStore } from '../lib/store'
import ScenarioControls from '../components/ScenarioControls'
import TriageQueue from '../components/TriageQueue'
import Approvals from '../components/Approvals'
import AgentLog from '../components/AgentLog'

export default function CommandCenter() {
  const snap = useStore((s) => s.snap)
  return (
    <div className="scanlines vignette flex h-full flex-col overflow-hidden">
      <div className="sweep" />
      <Header>
        <ScenarioControls />
      </Header>
      <main className="relative flex min-h-0 flex-1">
        <aside className="z-10 flex w-[350px] shrink-0 flex-col gap-2 p-2"><TriageQueue /></aside>
        <section className="relative min-w-0 flex-1"><ScenePane /></section>
        <aside className="z-10 flex w-[390px] shrink-0 flex-col gap-2 p-2"><Approvals /><AgentLog /></aside>
      </main>
      {!snap && <div className="absolute inset-0 grid place-items-center font-mono text-cyan/50">ESTABLISHING LINK…</div>}
    </div>
  )
}
