import { useStore } from '../lib/store'
export default function CommandCenter() {
  const snap = useStore((s) => s.snap)
  const link = useStore((s) => s.link)
  return <div className="p-6 font-mono">HOLOSAFE · link {link} · version {snap?.version ?? '-'}</div>
}
