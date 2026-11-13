/**
 * Поиск домов: `GET /api/houses?q=`.
 *
 * Что живёт здесь, а не в компонентах:
 * - предыдущий запрос отменяется при новом вводе, чтобы медленный ответ не
 *   перезаписал свежий (гонка «Пе» → «Первая речка»);
 * - в сеть уходит debounced-значение: пауза 250 мс, не каждый символ;
 * - «ничего не найдено» и «запрос упал» — разные состояния;
 * - `isPending` отделяет «данные ещё в пути» от «данные есть». Без него после
 *   очистки поля на 250 мс видно «Найдено: 0» и пустое состояние, хотя запрос
 *   ещё даже не ушёл.
 */
import { useCallback, useEffect, useState } from 'react'

import { ApiError, searchHouses } from '../../api/client'
import type { HouseSummary } from '../../types'
import { normalizeQuery } from '../../lib/normalize'
import { useDebouncedValue } from '../../lib/useDebouncedValue'

const DEBOUNCE_MS = 250

export type SearchStatus = 'loading' | 'ready' | 'error'

export interface UseHouseSearchResult {
  query: string
  setQuery: (value: string) => void
  items: HouseSummary[]
  total: number
  status: SearchStatus
  /** Запрос по текущему вводу ещё не завершился: показывать скелетон/«Ищем…». */
  isPending: boolean
  /** Текст ошибки для пользователя; `null`, когда ошибки нет. */
  error: string | null
  retry: () => void
}

export function useHouseSearch(): UseHouseSearchResult {
  const [query, setQuery] = useState('')
  const [items, setItems] = useState<HouseSummary[]>([])
  const [total, setTotal] = useState(0)
  const [status, setStatus] = useState<SearchStatus>('loading')
  const [error, setError] = useState<string | null>(null)
  const [appliedQuery, setAppliedQuery] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)
  const debouncedQuery = useDebouncedValue(query, DEBOUNCE_MS)

  useEffect(() => {
    const effective = normalizeQuery(debouncedQuery)
    const controller = new AbortController()
    setStatus('loading')
    setError(null)

    searchHouses(effective, controller.signal)
      .then((response) => {
        // Ответ мог прийти уже после того, как пользователь набрал другое:
        // без этой проверки медленный ответ перезаписывает свежий список.
        if (controller.signal.aborted) return
        setItems(response.items)
        setTotal(response.total)
        setAppliedQuery(effective)
        setStatus('ready')
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        // Фиксируем, что попытка по этому запросу завершилась: иначе
        // `isPending` останется `true` и ошибка не покажется никогда.
        setAppliedQuery(effective)
        setError(cause instanceof ApiError ? cause.message : 'не удалось загрузить список домов')
        setStatus('error')
      })

    // Размонтирование и новый запрос отменяют предыдущий: его ответ уже не нужен.
    return () => controller.abort()
  }, [debouncedQuery, reloadToken])

  const retry = useCallback(() => setReloadToken((token) => token + 1), [])

  const isPending = status === 'loading' || appliedQuery !== normalizeQuery(query)

  return { query, setQuery, items, total, status, isPending, error, retry }
}
