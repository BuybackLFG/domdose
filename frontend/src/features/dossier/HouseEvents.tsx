import { useState } from 'react';
import { categoryLabel, formatDateTime } from './format';
import type { HouseEvent, UtilityCategory } from './types';

const PAGE_SIZE = 5;

type EventFilter = 'all' | UtilityCategory;

const FILTERS: readonly EventFilter[] = ['all', 'hot_water', 'cold_water', 'electricity', 'heating'];

interface HouseEventsProps {
  /** События в порядке ответа API: от новых к старым. */
  events: readonly HouseEvent[];
}

function filterLabel(filter: EventFilter): string {
  return filter === 'all' ? 'Все' : categoryLabel(filter);
}

function matchesFilter(event: HouseEvent, filter: EventFilter): boolean {
  return filter === 'all' || event.category === filter;
}

function eventKey(event: HouseEvent, index: number): string {
  return [
    event.house_id,
    event.category,
    event.started_at,
    event.ended_at ?? 'ongoing',
    event.source_url,
    index,
  ].join('|');
}

export function HouseEvents({ events }: HouseEventsProps) {
  const [filter, setFilter] = useState<EventFilter>('all');
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const filtered = events.filter((event) => matchesFilter(event, filter));
  const visible = filtered.slice(0, visibleCount);

  const selectFilter = (next: EventFilter) => {
    setFilter(next);
    setVisibleCount(PAGE_SIZE);
  };

  return (
    <section aria-labelledby="house-events-heading" className="rounded-2xl bg-surface p-4 shadow-sm ring-1 ring-border sm:p-5">
      <h2 id="house-events-heading" className="text-base font-semibold text-text">
        События дома
      </h2>

      {events.length === 0 ? (
        <p className="mt-3 rounded-xl bg-surface-subtle px-3 py-2 text-sm text-text-secondary">
          В использованном источнике нет зафиксированных отключений за период. Это не доказывает
          их отсутствие.
        </p>
      ) : (
        <>
          <div role="group" aria-label="Фильтр событий" className="mt-3 flex flex-wrap gap-2">
            {FILTERS.map((option) => {
              const selected = option === filter;
              return (
                <button
                  key={option}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => selectFilter(option)}
                  className={`min-h-9 rounded-full border px-3 text-sm font-medium transition ${
                    selected
                      ? 'border-accent bg-accent text-white'
                      : 'border-border bg-surface text-text hover:border-accent hover:bg-surface-subtle'
                  }`}
                >
                  {filterLabel(option)}
                </button>
              );
            })}
          </div>

          {filtered.length === 0 ? (
            <p className="mt-3 rounded-xl bg-surface-subtle px-3 py-2 text-sm text-text-secondary">
              Нет событий этой категории за период.
            </p>
          ) : (
            <ul aria-label="События дома" className="mt-3 space-y-2">
              {visible.map((event, index) => (
                <li key={eventKey(event, index)} className="rounded-xl border border-border bg-surface-subtle px-3 py-2">
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-sm font-medium text-text">{categoryLabel(event.category)}</p>
                      <p className="mt-1 text-sm text-text-secondary">
                        {formatDateTime(event.started_at)} —{' '}
                        {event.ended_at === null ? 'Продолжается' : formatDateTime(event.ended_at)}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      <span className="rounded-full bg-surface px-2 py-1 text-xs text-text-secondary ring-1 ring-border">
                        {event.kind === 'emergency' ? 'Аварийное' : 'Плановое'}
                      </span>
                      {event.is_mass && (
                        <span className="rounded-full bg-accent-soft px-2 py-1 text-xs text-accent ring-1 ring-accent/20">
                          Массовое
                        </span>
                      )}
                      {event.is_natural_disaster && (
                        <span className="rounded-full bg-warning/10 px-2 py-1 text-xs text-warning ring-1 ring-warning/25">
                          Стихийное
                        </span>
                      )}
                    </div>
                  </div>
                  <a
                    href={event.source_url}
                    target="_blank"
                    rel="noopener noreferrer nofollow"
                    className="mt-2 inline-block text-xs font-medium text-accent hover:text-accent-hover"
                  >
                    Источник
                  </a>
                </li>
              ))}
            </ul>
          )}

          {visible.length < filtered.length && (
            <button
              type="button"
              onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}
              className="mt-3 min-h-11 rounded-xl border border-border bg-surface px-4 text-sm font-medium text-accent transition hover:border-accent hover:bg-surface-subtle"
            >
              Показать ещё
            </button>
          )}
        </>
      )}
    </section>
  );
}
