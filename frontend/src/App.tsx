import { useEffect, useState } from 'react'
import type { HealthResponse } from './types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type Status = 'loading' | 'ok' | 'error'

export default function App() {
  const [status, setStatus] = useState<Status>('loading')

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((res) => (res.ok ? (res.json() as Promise<HealthResponse>) : Promise.reject(res.status)))
      .then((data) => setStatus(data.status === 'ok' ? 'ok' : 'error'))
      .catch(() => setStatus('error'))
  }, [])

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center">
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-8 text-center">
        <h1 className="text-2xl font-semibold">ДомДосье</h1>
        <p className="mt-2 text-sm text-slate-400">Каркас фронтенда. API: {API_URL}</p>
        <p className="mt-4 text-sm">
          backend:{' '}
          <span className={status === 'ok' ? 'text-emerald-400' : 'text-rose-400'}>{status}</span>
        </p>
      </div>
    </main>
  )
}
