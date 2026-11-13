/**
 * Чистые правила маршрутов. Вынесены из `router.ts`, чтобы их можно было
 * тестировать без DOM и без React.
 */

export const ROUTES = {
  search: '/',
  house: (id: string) => `/house/${encodeURIComponent(id)}`,
} as const

/**
 * `/house/svetlanskaya-37` → `'svetlanskaya-37'`.
 * `/house/`, `/houses/x`, `/` → `null`. Битая percent-кодировка → `null`,
 * чтобы кривой URL давал 404, а не исключение в рендере.
 */
export function matchHouseId(pathname: string): string | null {
  const match = /^\/house\/([^/]+)\/?$/.exec(pathname)
  if (!match?.[1]) return null
  try {
    const id = decodeURIComponent(match[1])
    return id === '' ? null : id
  } catch {
    return null
  }
}
