import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import NotImplemented from './pages/NotImplemented'
import SystemHealth from './pages/SystemHealth'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<NotImplemented title="Dashboard" step={9} />} />
        <Route path="cameras" element={<NotImplemented title="Cameras" step={9} />} />
        <Route path="incidents" element={<NotImplemented title="Incidents" step={10} />} />
        <Route path="alerts" element={<NotImplemented title="Alerts" step={10} />} />
        <Route path="health" element={<SystemHealth />} />
        <Route path="settings" element={<NotImplemented title="Settings" step={10} />} />
        <Route path="*" element={<NotImplemented title="Page not found" step={1} />} />
      </Route>
    </Routes>
  )
}
