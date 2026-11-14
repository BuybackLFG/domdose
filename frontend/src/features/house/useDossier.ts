/**
 * Загрузка досье: `GET /api/houses/{id}` (B2).
 *
 * Три исхода, которые нельзя сливать в один:
 * - `notFound` — дом не найден (404), показываем «досье не найдено»;
 * - `error` — запрос упал, показываем текст и кнопку «Повторить»;
 * - `ready` — данные есть.
 *
 * Ответ, пришедший после смены дома или размонтирования, отбрасывается: иначе
 * медленное досье прошлого дома перезапишет текущее.
 */
import { useCallback, useEffect, useState } from 'react'

import { ApiError, getHouseDossier } from '../../api/client'
import type { Dossier } from '../../types'

export type DossierStatus = 'loading' | 'ready' | 'notFound' | 'error'

export interface UseDossierResult {
  status: DossierStatus
  dossier: Dossier | null
  error: string | null
  retry: () => void
}

export function useDossier(houseId: string): UseDossierResult {
  const [status, setStatus] = useState<DossierStatus>('loading')
  const [dossier, setDossier] = useState<Dossier | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    // Смена дома — это заново «загрузка», а не показ прошлого досье.
    setStatus('loading')
    setError(null)

    getHouseDossier(houseId, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) return
        setDossier(response)
        setStatus('ready')
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        setDossier(null)
        if (cause instanceof ApiError && cause.status === 404) {
          setStatus('notFound')
          return
        }
        setError(cause instanceof ApiError ? cause.message : 'не удалось загрузить досье дома')
        setStatus('error')
      })

    return () => controller.abort()
  }, [houseId, reloadToken])

  const retry = useCallback(() => setReloadToken((token) => token + 1), [])

  return { status, dossier, error, retry }
}
