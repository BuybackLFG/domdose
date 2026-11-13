import { useEffect, useState } from 'react'

/**
 * Отдаёт `value`, но только после того, как оно не менялось `delayMs`.
 * Первый рендер возвращает исходное значение сразу: пустой запрос не должен
 * задерживать загрузку датасета на старте.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    if (value === debounced) return
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs, debounced])

  return debounced
}
