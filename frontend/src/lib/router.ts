/** Роутер на History API: без новых зависимостей в package.json. */
import { useEffect, useState, type MouseEvent } from 'react'

export { ROUTES, matchHouseId } from './routes'

export function usePathname(): string {
  const [pathname, setPathname] = useState(() => window.location.pathname)

  useEffect(() => {
    const onPopState = (): void => setPathname(window.location.pathname)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  return pathname
}

/** Переход без перезагрузки; на чужой origin уходим обычной навигацией. */
export function navigate(to: string): void {
  const target = new URL(to, window.location.origin)
  if (target.origin !== window.location.origin) {
    window.location.assign(target.href)
    return
  }
  const next = `${target.pathname}${target.search}${target.hash}`
  if (next === `${window.location.pathname}${window.location.search}${window.location.hash}`) return
  window.history.pushState({}, '', next)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

/**
 * Обычный левый клик без модификаторов.
 *
 * Cmd/Ctrl/Shift/Alt и остальные кнопки мыши остаются браузеру: «открыть в
 * новой вкладке» должно работать так, как ожидает пользователь.
 */
export function isPlainClick(event: MouseEvent<HTMLAnchorElement>): boolean {
  if (event.defaultPrevented) return false
  if (event.button !== 0) return false
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false
  return true
}

/** Перехватывает обычный левый клик без модификаторов. */
export function interceptClick(event: MouseEvent<HTMLAnchorElement>, to: string): void {
  if (!isPlainClick(event)) return
  event.preventDefault()
  navigate(to)
}
