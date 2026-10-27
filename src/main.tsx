import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import QuantDashboard from './views/admin/quant-dashboard'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QuantDashboard />
  </StrictMode>,
)
