/**
 * Чек-лист вопросов продавцу (DD-25, F4).
 *
 * Вопросы приходят из API (`items`), экран только отмечает их и позволяет
 * добавить свои. Ничего не отправляется на сервер: состояние лежит в
 * localStorage по дому, поэтому у каждого дома свой прогресс.
 *
 * Вся логика (ключ, разбор, дедупликация, прогресс) — в `storage.ts` и
 * `progress.ts` без React: их проще тестировать и они не падают там, где нет
 * `localStorage`.
 */
import { useId, useState, type FormEvent } from 'react'

import { computeProgress } from './progress'
import {
  MAX_QUESTION_LENGTH,
  addCustomQuestion,
  emptyChecklist,
  loadChecklist,
  mergeRows,
  removeCustomQuestion,
  saveChecklist,
  toggleChecked,
  type ChecklistState,
} from './storage'
import type { ChecklistItem } from '../../types'

interface ChecklistSectionProps {
  houseId: string
  items: ChecklistItem[]
}

/**
 * `key={houseId}` сбрасывает состояние при переходе на другой дом: иначе
 * первая отрисовка нового дома успела бы записать отметки старого дома в его
 * ключ localStorage.
 */
export function ChecklistSection({ houseId, items }: ChecklistSectionProps) {
  return <ChecklistEditor key={houseId} houseId={houseId} items={items} />
}

function ChecklistEditor({ houseId, items }: ChecklistSectionProps) {
  // Ленивый useState: localStorage читается при первом рендере, а не на
  // уровне модуля — иначе тесты узла и SSR упали бы.
  const [state, setState] = useState<ChecklistState>(() => loadChecklist(houseId))
  const [draft, setDraft] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  const formId = useId()
  const listId = useId()
  const hintId = useId()

  const rows = mergeRows(items, state.custom)

  const progress = computeProgress(
    rows.map((row) => row.id),
    state.checked,
  )
  const isChecked = (id: string): boolean => state.checked.includes(id)
  const isDirty = state.checked.length > 0 || state.custom.length > 0

  const update = (next: ChecklistState): void => {
    setState(next)
    saveChecklist(houseId, next)
  }

  const onToggle = (id: string): void => {
    setMessage(null)
    update(toggleChecked(state, id))
  }

  const onRemove = (id: string): void => {
    setMessage(null)
    update(removeCustomQuestion(state, id))
  }

  const onReset = (): void => {
    setDraft('')
    setMessage(null)
    update(emptyChecklist())
  }

  const onAdd = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault()
    const result = addCustomQuestion(state, draft, rows.map((row) => row.question))
    if (!result.ok) {
      setMessage(
        result.error === 'empty'
          ? 'Введите вопрос: пустую строку добавить нельзя.'
          : 'Такой вопрос уже есть в списке.',
      )
      return
    }
    update(result.state)
    setDraft('')
    setMessage(null)
  }

  return (
    <section aria-labelledby={`${formId}-title`} className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id={`${formId}-title`} className="text-sm font-semibold text-slate-300">
          Вопросы продавцу
        </h2>
        <p className="text-xs text-slate-500" aria-live="polite">
          Отмечено {progress.checked} из {progress.total}
        </p>
      </div>

      <div className="space-y-1.5">
        {progress.total > 0 && (
          <div
            role="progressbar"
            aria-label="Прогресс чек-листа"
            aria-valuenow={progress.checked}
            aria-valuemin={0}
            aria-valuemax={progress.total}
            aria-valuetext={`${progress.checked} из ${progress.total}`}
            className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800"
          >
            <div
              className="h-full rounded-full bg-emerald-500 transition-[width]"
              style={{ width: `${progress.percent}%` }}
            />
          </div>
        )}
        <p className="text-xs text-slate-500">
          {progress.total === 0
            ? 'Пока нечего отмечать — добавьте свой вопрос.'
            : progress.checked === progress.total
              ? 'Все вопросы пройдены. Хорошо бы ещё раз сверить с продавцом.'
              : 'Галочки сохраняются в этом браузере — можно вернуться позже.'}
        </p>
      </div>

      {rows.length === 0 ? (
        <p className="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-6 text-center text-sm text-slate-400">
          Вопросов пока нет: по открытым данным этот дом ничем не зацепился. Добавьте
          свой вопрос — он сохранится только у вас.
        </p>
      ) : (
        <ul
          id={listId}
          className="divide-y divide-slate-800/70 overflow-hidden rounded-xl border border-slate-800 bg-slate-900/50"
        >
          {rows.map((row) => {
            const checkboxId = `${listId}-${row.id}`
            const reasonId = `${checkboxId}-reason`
            return (
              <li key={row.id} className="px-4 py-3">
                <div className="flex items-start gap-3">
                  <input
                    id={checkboxId}
                    type="checkbox"
                    checked={isChecked(row.id)}
                    onChange={() => onToggle(row.id)}
                    aria-describedby={row.reason !== null ? reasonId : undefined}
                    className="mt-0.5 size-4 shrink-0 accent-emerald-500"
                  />
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <label
                      htmlFor={checkboxId}
                      className="block cursor-pointer text-sm break-words text-slate-200"
                    >
                      {row.question}
                    </label>

                    {row.reason !== null && (
                      <details id={reasonId} className="group text-xs text-slate-400">
                        <summary className="cursor-pointer list-none text-slate-500 hover:text-slate-300">
                          <span aria-hidden="true" className="inline-block group-open:hidden">
                            +
                          </span>
                          <span aria-hidden="true" className="hidden group-open:inline">
                            −
                          </span>{' '}
                          Почему этот вопрос
                        </summary>
                        <p className="mt-1.5 break-words border-l border-slate-700 pl-3">
                          {row.reason}
                        </p>
                        {row.sourceEventIds.length > 0 && (
                          <p className="mt-1 break-all text-slate-500">
                            События:{' '}
                            {row.sourceEventIds.map((eventId) => (
                              <code
                                key={eventId}
                                className="mr-1.5 rounded bg-slate-800 px-1 py-0.5 font-mono text-[11px] text-slate-300"
                              >
                                {eventId}
                              </code>
                            ))}
                          </p>
                        )}
                      </details>
                    )}

                    {row.custom && (
                      <button
                        type="button"
                        onClick={() => onRemove(row.id)}
                        className="text-xs text-slate-500 underline-offset-2 hover:text-rose-300 hover:underline"
                      >
                        Удалить свой вопрос
                      </button>
                    )}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}

      <form onSubmit={onAdd} className="flex flex-col gap-2 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1">
          <label htmlFor={`${formId}-input`} className="sr-only">
            Свой вопрос продавцу
          </label>
          <input
            id={`${formId}-input`}
            type="text"
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value)
              setMessage(null)
            }}
            maxLength={MAX_QUESTION_LENGTH}
            placeholder="Например: когда меняли стояки в подъезде?"
            aria-invalid={message !== null}
            aria-describedby={message !== null ? `${formId}-message` : hintId}
            className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/30"
          />
        </div>
        <button
          type="submit"
          className="shrink-0 rounded-xl border border-emerald-700 bg-emerald-900/40 px-3 py-2 text-sm text-emerald-100 hover:bg-emerald-900/70"
        >
          Добавить вопрос
        </button>
      </form>

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p
          id={`${formId}-message`}
          aria-live="polite"
          className={`min-h-5 text-xs ${message === null ? 'text-slate-500' : 'text-amber-300'}`}
        >
          {message ?? (
            <span id={hintId}>Свой вопрос виден только вам и только в этом браузере.</span>
          )}
        </p>
        <div className="flex shrink-0 flex-col items-start gap-1 sm:items-end">
          <button
            type="button"
            onClick={onReset}
            disabled={!isDirty}
            aria-describedby={`${formId}-reset-hint`}
            className="shrink-0 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Сбросить
          </button>
          <span id={`${formId}-reset-hint`} className="text-[11px] leading-snug text-slate-500">
            снимет отметки и удалит свои вопросы
          </span>
        </div>
      </div>
    </section>
  )
}
