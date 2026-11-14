/** Типизированный клиент API. Все запросы к backend идут только отсюда. */
import type { Dossier, ErrorResponse, HouseList } from '../types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

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
  return request<HouseList>(`/api/houses?q=${encodeURIComponent(query)}`, signal)
}

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
  return request<Dossier>(`/api/houses/${encodeURIComponent(id)}`, signal)
}
