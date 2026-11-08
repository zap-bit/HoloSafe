import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import CommandCenter from './pages/CommandCenter'
import Holo from './pages/Holo'
import ReportPage from './pages/Report'
import { startLink } from './lib/ws'

startLink()

createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
      <Routes>
        <Route path="/" element={<CommandCenter />} />
        <Route path="/holo" element={<Holo />} />
        <Route path="/report" element={<ReportPage />} />
      </Routes>
  </BrowserRouter>
,
)
