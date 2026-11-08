import { useState } from 'react'
/** Uses frontend/public/logo.(png|jpg|webp|svg) — first one that exists wins. Owner drops in the real art. */
const CANDIDATES = ['/logo.png', '/logo.webp', '/logo.jpg', '/logo.svg']
export default function Logo({ className = '' }: { className?: string }) {
  const [i, setI] = useState(0)
  return <img src={CANDIDATES[i]} alt="HoloSafe" className={className} onError={() => i < CANDIDATES.length - 1 && setI(i + 1)} />
}
