/**
 * Первый экран демо: поиск адреса (DD-22, F1).
 *
 * Доступность: это combobox, поэтому стрелки и Enter имеют смысл только вместе
 * с `role="combobox"` + `aria-activedescendant` — иначе скринридер объявляет
 * ввод обычным текстовым полем и не знает про список.
 */
import { useEffect, useId, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'

import { Highlight } from './highlight'
import { enterIndex, nextIndex } from './selection'
import { useHouseSearch } from './useHouseSearch'
import { ROUTES, interceptClick, navigate } from '../../lib/router'
import type { HouseSummary } from '../../types'

function IndexBadge({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) {
    return (
      <span className="shrink-0 text-xs text-slate-500" title="Индекс ещё не посчитан">
        без индекса
      </span>
    )
  }
  return (
    <span className="shrink-0 rounded-md bg-slate-800 px-2 py-0.5 font-mono text-sm text-emerald-300">
      {value}
    </span>
  )
}

function ResultRow({
  house,
  query,
  active,
  optionId,
  onActivate,
}: {
  house: HouseSummary
  query: string
  active: boolean
  optionId: string
  onActivate: () => void
}) {
  const href = ROUTES.house(house.id)

  return (
    <li
      id={optionId}
      role="option"
      aria-selected={active}
      // Мышь подсвечивает, но не «выбирает»: иначе наведение перебивает
      // клавиатуру, и Enter открывает не то, что подсвечено стрелками.
      onMouseMove={onActivate}
      className={`border-l-2 transition-colors ${
        active ? 'border-emerald-400 bg-slate-800/80' : 'border-transparent'
      }`}
    >
      <a
        href={href}
        onClick={(event: MouseEvent<HTMLAnchorElement>) => interceptClick(event, href)}
        className="flex items-baseline justify-between gap-3 px-3 py-2.5 no-underline hover:bg-slate-800/40"
      >
        <span className="min-w-0">
          <span className="block truncate text-slate-100">
            <Highlight text={house.address} query={query} />
          </span>
          <span className="block truncate text-xs text-slate-400">
            <Highlight text={house.district} query={query} /> район
          </span>
        </span>
        <IndexBadge value={house.index} />
      </a>
    </li>
  )
}

export function SearchPage() {
  const search = useHouseSearch()
  const [activeIndex, setActiveIndex] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const listId = useId()
  const optionId = (index: number): string => `${listId}-option-${index}`

  const count = search.items.length

  // Пришёл новый список — прежний активный индекс относится к другому списку.
  useEffect(() => {
    setActiveIndex(-1)
  }, [search.items])

  const open = (house: HouseSummary): void => navigate(ROUTES.house(house.id))

  const move = (delta: number): void => {
    setActiveIndex((current) => nextIndex(count, current, delta))
  }

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>): void => {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault()
        move(1)
        return
      case 'ArrowUp':
        event.preventDefault()
        move(-1)
        return
      case 'Home':
        if (count > 0) {
          event.preventDefault()
          setActiveIndex(0)
        }
        return
      case 'End':
        if (count > 0) {
          event.preventDefault()
          setActiveIndex(count - 1)
        }
        return
      case 'Enter': {
        // Enter без выбора открывает первый вариант: так работает любой
        // автокомплит, и демо не должно упираться в «сначала нажми стрелку».
        const index = enterIndex(count, activeIndex, search.query)
        const target = index >= 0 ? search.items[index] : undefined
        if (target) {
          event.preventDefault()
          open(target)
        }
        return
      }
      case 'Escape':
        if (search.query !== '') {
          event.preventDefault()
          search.setQuery('')
          setActiveIndex(-1)
          inputRef.current?.focus()
        }
        return
      default:
        return
    }
  }

  const isSearching = search.query.trim() !== ''
  // «Ничего не нашлось» — факт о готовом ответе. Пока запрос в пути (включая
  // паузу debounce), показывать пустое состояние нельзя: это не результат.
  const showEmpty = search.status === 'ready' && !search.isPending && count === 0

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 px-4 py-10 sm:py-16">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-100">ДомДосье</h1>
        <p className="text-sm text-slate-400">
          Досье на дом из открытых данных: индекс, история, чек-лист вопросов продавцу.
        </p>
      </header>

      <div>
        <label htmlFor="house-search" className="sr-only">
          Адрес или район
        </label>
        <input
          ref={inputRef}
          id="house-search"
          type="text"
          role="combobox"
          aria-expanded={count > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeIndex >= 0 ? optionId(activeIndex) : undefined}
          aria-describedby="house-search-status"
          autoComplete="off"
          spellCheck={false}
          placeholder="Светланская или Первореченский"
          value={search.query}
          onChange={(event) => search.setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-base text-slate-100 outline-none placeholder:text-slate-500 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/30"
        />
        <p id="house-search-status" className="mt-2 min-h-5 text-xs text-slate-500" aria-live="polite">
          {search.status === 'error'
            ? search.error
            : search.isPending
              ? 'Ищем…'
              : isSearching
                ? `Найдено: ${search.total}`
                : `Всего в каталоге: ${search.total}. Начните вводить адрес`}
        </p>
      </div>

      {search.status === 'error' && (
        <div
          role="alert"
          className="flex items-center justify-between gap-4 rounded-xl border border-rose-900/60 bg-rose-950/40 px-4 py-3 text-sm text-rose-200"
        >
          <span>Не удалось загрузить список домов.</span>
          <button
            type="button"
            onClick={search.retry}
            className="shrink-0 rounded-lg border border-rose-800 px-3 py-1.5 text-rose-100 hover:bg-rose-900/50"
          >
            Повторить
          </button>
        </div>
      )}

      {count > 0 && (
        <ul
          id={listId}
          role="listbox"
          aria-label="Найденные дома"
          aria-busy={search.isPending}
          className="divide-y divide-slate-800/70 overflow-hidden rounded-xl border border-slate-800 bg-slate-900/50"
        >
          {search.items.map((house, index) => (
            <ResultRow
              key={house.id}
              house={house}
              query={search.query}
              active={index === activeIndex}
              optionId={optionId(index)}
              onActivate={() => setActiveIndex(index)}
            />
          ))}
        </ul>
      )}

      {showEmpty && (
        <p className="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-6 text-center text-sm text-slate-400">
          По запросу «{search.query.trim()}» ничего не нашлось. Проверьте улицу или выберите район.
        </p>
      )}

      {search.status === 'ready' && count > 0 && (
        <p className="text-xs text-slate-500">
          <kbd className="rounded border border-slate-700 px-1">↑</kbd>{' '}
          <kbd className="rounded border border-slate-700 px-1">↓</kbd> — выбор,{' '}
          <kbd className="rounded border border-slate-700 px-1">Enter</kbd> — открыть,{' '}
          <kbd className="rounded border border-slate-700 px-1">Esc</kbd> — очистить.
        </p>
      )}
    </main>
  )
}
