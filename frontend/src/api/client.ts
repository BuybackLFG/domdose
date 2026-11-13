/** Типизированный клиент API. Все запросы к backend идут только отсюда. */
import type { Dossier, ErrorResponse, HouseList } from '../types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
/** Пока backend отвечает 501, фронтенд можно гонять на фикстурах. */
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as ErrorResponse).detail === 'string'
  )
}

/** Достаёт `detail` из тела ошибки; тело может быть чем угодно, включая 501-заглушку. */
async function readError(response: Response): Promise<ApiError> {
  let detail = `запрос не удался (${response.status})`
  try {
    const body: unknown = await response.json()
    if (isErrorResponse(body)) detail = body.detail
  } catch {
    // тело не JSON — остаётся только статус
  }
  return new ApiError(response.status, detail)
}

async function request<T>(path: string, signal: AbortSignal | null): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, signal ? { signal } : {})
  if (!response.ok) throw await readError(response)
  return (await response.json()) as T
}

/** `GET /api/houses?q=` — поиск домов (B1). Пустой `q` возвращает весь датасет. */
export async function searchHouses(
  query: string,
  signal: AbortSignal | null = null,
): Promise<HouseList> {
  if (USE_MOCKS) {
    // Динамический импорт: фикстуры не попадают в основной бандл и не
    // загружаются, когда флаг выключен.
    const { mockSearchHouses } = await import('../mocks/houses')
    return mockSearchHouses(query, signal)
  }
  return request<HouseList>(`/api/houses?q=${encodeURIComponent(query)}`, signal)
}

/** Текст 404 досье — дословно из контракта (`schemas/errors.py`). */
const HOUSE_NOT_FOUND = 'house not found'

/**
 * `GET /api/houses/{id}` — досье дома (B2).
 *
 * Неизвестный id — это `ApiError` со `status === 404`, а не `null`: вызывающий
 * код обязан отличать «дома нет» от «запрос не дошёл».
 */
export async function getHouseDossier(
  id: string,
  signal: AbortSignal | null = null,
): Promise<Dossier> {
  if (USE_MOCKS) {
    const { mockHouseDossier } = await import('../mocks/dossier')
    return mockHouseDossier(id, signal).then((dossier) => {
      if (!dossier) throw new ApiError(404, HOUSE_NOT_FOUND)
      return dossier
    })
  }
  return request<Dossier>(`/api/houses/${encodeURIComponent(id)}`, signal)
}
