import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './style.css'
const telegram = (window as Window & {
  Telegram?: { WebApp?: { ready?: () => void; expand?: () => void } }
}).Telegram?.WebApp
telegram?.ready?.()
telegram?.expand?.()
createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
