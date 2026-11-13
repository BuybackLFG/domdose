/**
 * Локальное состояние чек-листа: ключ, разбор, нормализация, добавление.
 *
 * Здесь нет React и нет обращений к `localStorage` на уровне модуля: чистые
 * функции принимают и отдают строки/объекты. Так их можно тестировать в Node,
 * где `localStorage` не существует, и так экран не падает на SSR. Доступ к
 * браузерному хранилищу — только в `loadChecklist` / `saveChecklist`, которые
 * вызываются из компонента (ленивый `useState` и `useEffect`).
 *
 * Внутри хранится только то, чего нет в API: отмеченные id из API (сами
 * вопросы приходят с сервера) и свои вопросы, добавленные вручную.
 */
import type { ChecklistItem } from '../../types'

/** Префикс ключа localStorage. Полный ключ — по дому: `<префикс><house_id>`. */
export const STORAGE_PREFIX = 'domdose:checklist:'

/** Свой вопрос, добавленный вручную. `id` нужен только как ключ списка и отметки. */
export interface CustomQuestion {
  id: string
  question: string
}

/** Сохранённое состояние одного дома. */
export interface ChecklistState {
  /** id отмеченных вопросов из API. */
  checked: string[]
  /** Свои вопросы. Порядок добавления сохраняется. */
  custom: CustomQuestion[]
}

/** Максимум символов в своём вопросе: защита от случайной вставки простыни. */
export const MAX_QUESTION_LENGTH = 200

export function emptyChecklist(): ChecklistState {
  return { checked: [], custom: [] }
}

/** Ключ localStorage для дома. Разные дома не пересекаются даже при общем id. */
export function storageKey(houseId: string): string {
  return `${STORAGE_PREFIX}${houseId}`
}

/**
 * Ключ сравнения вопросов: регистр, ё→е и лишние пробелы не делают вопрос
 * новым. Исходный текст не меняется — нормализация нужна только для проверки.
 */
export function normalizeQuestion(text: string): string {
  return text.toLowerCase().replace(/ё/g, 'е').replace(/\s+/g, ' ').trim()
}

/** Обрезка до лимита по символам (не по байтам), чтобы поле и хранилище совпали. */
export function clampQuestion(text: string): string {
  const trimmed = text.trim()
  return trimmed.length > MAX_QUESTION_LENGTH
    ? trimmed.slice(0, MAX_QUESTION_LENGTH).trimEnd()
    : trimmed
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function uniqueStrings(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const result: string[] = []
  for (const entry of value) {
    if (typeof entry !== 'string') continue
    const id = entry.trim()
    if (id === '' || result.includes(id)) continue
    result.push(id)
  }
  return result
}

function uniqueCustom(value: unknown): CustomQuestion[] {
  if (!Array.isArray(value)) return []
  const result: CustomQuestion[] = []
  const seen = new Set<string>()
  for (const entry of value) {
    if (!isRecord(entry)) continue
    const id = typeof entry.id === 'string' ? entry.id.trim() : ''
    const question = typeof entry.question === 'string' ? clampQuestion(entry.question) : ''
    if (id === '' || question === '') continue
    const key = normalizeQuestion(question)
    if (seen.has(key)) continue
    seen.add(key)
    result.push({ id, question })
  }
  return result
}

/**
 * Разбор сохранённой строки. Битый JSON, чужой формат, `null` — это пустое
 * состояние, а не исключение: белый экран из-за мусора в localStorage хуже,
 * чем потерянные галочки.
 */
export function parseChecklist(raw: string | null | undefined): ChecklistState {
  if (typeof raw !== 'string' || raw.trim() === '') return emptyChecklist()

  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return emptyChecklist()
  }
  if (!isRecord(data)) return emptyChecklist()

  return {
    checked: uniqueStrings(data.checked),
    custom: uniqueCustom(data.custom),
  }
}

/** Сериализация состояния. Только то, что читает `parseChecklist`. */
export function serializeChecklist(state: ChecklistState): string {
  return JSON.stringify({ checked: state.checked, custom: state.custom })
}

/** `loadChecklist`/`saveChecklist` — единственные места, знающие про storage. */
function browserStorage(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    // Приватный режим некоторых браузеров бросает уже на чтении объекта.
    return null
  }
}

/** Загрузить состояние дома. Ошибки хранилища не должны ломать экран. */
export function loadChecklist(houseId: string): ChecklistState {
  const storage = browserStorage()
  if (storage === null) return emptyChecklist()
  try {
    return parseChecklist(storage.getItem(storageKey(houseId)))
  } catch {
    return emptyChecklist()
  }
}

/** Сохранить состояние дома. Переполнение квоты не должно ломать экран. */
export function saveChecklist(houseId: string, state: ChecklistState): void {
  const storage = browserStorage()
  if (storage === null) return
  try {
    storage.setItem(storageKey(houseId), serializeChecklist(state))
  } catch {
    // Молча: чек-лист продолжает работать в памяти до перезагрузки.
  }
}

export type AddQuestionResult =
  | { ok: true; state: ChecklistState; question: string }
  | { ok: false; error: 'empty' | 'duplicate' }

/**
 * Добавить свой вопрос.
 *
 * `taken` — вопросы, которые уже видны в списке (из API и свои). Пустая
 * строка и дубль не добавляются; текст вопроса возвращается исходный (только
 * trim), а сравнивается нормализованный.
 */
export function addCustomQuestion(
  state: ChecklistState,
  text: string,
  taken: readonly string[],
): AddQuestionResult {
  const question = clampQuestion(text)
  if (question === '') return { ok: false, error: 'empty' }

  const key = normalizeQuestion(question)
  const existing = [...state.custom.map((item) => item.question), ...taken]
  if (existing.some((item) => normalizeQuestion(item) === key)) {
    return { ok: false, error: 'duplicate' }
  }

  return {
    ok: true,
    question,
    state: {
      checked: state.checked,
      custom: [...state.custom, { id: createCustomId(), question }],
    },
  }
}

/** Убрать свой вопрос вместе с его отметкой. */
export function removeCustomQuestion(state: ChecklistState, id: string): ChecklistState {
  return {
    checked: state.checked.filter((checkedId) => checkedId !== id),
    custom: state.custom.filter((item) => item.id !== id),
  }
}

/** Отметить/снять вопрос. Отметок может быть больше, чем вопросов: лишние не считаются. */
export function toggleChecked(state: ChecklistState, id: string): ChecklistState {
  const checked = state.checked.includes(id)
    ? state.checked.filter((checkedId) => checkedId !== id)
    : [...state.checked, id]
  return { checked, custom: state.custom }
}

function createCustomId(): string {
  return `custom-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

/** Вопросы API без дублей по нормализованному тексту, в порядке появления. */
export function apiQuestions(items: readonly ChecklistItem[]): ChecklistItem[] {
  const result: ChecklistItem[] = []
  const seen = new Set<string>()
  for (const item of items) {
    const key = normalizeQuestion(item.question)
    if (key === '' || seen.has(key)) continue
    seen.add(key)
    result.push(item)
  }
  return result
}

/** Строка чек-листа: вопрос API или свой, уже приведённые к общему виду. */
export interface ChecklistRow {
  id: string
  question: string
  /** `null` у своих вопросов: причины и событий у них нет. */
  reason: string | null
  sourceEventIds: string[]
  custom: boolean
}

/**
 * Слить вопросы API и свои в один список без дублей.
 *
 * Своё состояние живёт в localStorage и может пережить изменение API: если
 * такой же вопрос теперь пришёл с сервера, показываем версию из API (у неё
 * есть причина и события), а свою копию прячем. Иначе вопрос был бы дважды.
 */
export function mergeRows(
  items: readonly ChecklistItem[],
  custom: readonly CustomQuestion[],
): ChecklistRow[] {
  const rows: ChecklistRow[] = []
  const seen = new Set<string>()

  for (const item of apiQuestions(items)) {
    seen.add(normalizeQuestion(item.question))
    rows.push({
      id: item.id,
      question: item.question,
      reason: item.reason,
      sourceEventIds: item.source_event_ids ?? [],
      custom: false,
    })
  }

  for (const item of custom) {
    const question = clampQuestion(item.question)
    const key = normalizeQuestion(question)
    if (key === '' || seen.has(key)) continue
    seen.add(key)
    rows.push({ id: item.id, question, reason: null, sourceEventIds: [], custom: true })
  }

  return rows
}
