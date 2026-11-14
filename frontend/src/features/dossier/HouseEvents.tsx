import { useEffect, useRef, useState } from 'react';
import { categoryLabel, formatDateTime } from './format';
import type { HouseEvent, UtilityCategory } from './types';

const PAGE_SIZE = 5;

type EventFilter = 'all' | UtilityCategory;

const FILTERS: readonly EventFilter[] = ['all', 'hot_water', 'cold_water', 'electricity', 'heating'];

interface HouseEventsProps {
  /** События в порядке ответа API: от новых к старым. */
  events: readonly HouseEvent[];
  status: 'loading' | 'error' | 'success';
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

export function HouseEvents({ events, status }: HouseEventsProps) {
  const [filter, setFilter] = useState<EventFilter>('all');
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const listRef = useRef<HTMLUListElement | null>(null);
  const moreButtonRef = useRef<HTMLButtonElement | null>(null);
  // Индекс первого пункта, показанного последним нажатием «Показать ещё».
  const pendingFocusIndexRef = useRef<number | null>(null);

  const filtered = events.filter((event) => matchesFilter(event, filter));
  const visible = filtered.slice(0, visibleCount);

  const selectFilter = (next: EventFilter) => {
    pendingFocusIndexRef.current = null;
    setFilter(next);
    setVisibleCount(PAGE_SIZE);
  };

  useEffect(() => {
    const index = pendingFocusIndexRef.current;
    if (index === null) return;
    pendingFocusIndexRef.current = null;
    // Кнопка ещё на месте: фокус остаётся на ней.
    if (moreButtonRef.current !== null) return;
    const item = listRef.current?.children[index];
    if (item instanceof HTMLElement) item.focus();
  }, [visibleCount]);

  return (
    <section id="events" aria-labelledby="house-events-heading" className="section" data-screen="free">
      <div className="wrap">
        <div className="section-head">
          <h2 id="house-events-heading">События дома</h2>
          <p className="t-small muted">
            Записи из публичных объявлений за период выборки. Пустой список не доказывает
            отсутствие отключений.
          </p>
        </div>

        {status === 'loading' && (
          <div role="status" className="stack-5">
            <p className="loading-pulse t-small muted">Загружаем события…</p>
            <div aria-hidden="true" className="stack-3">
              {Array.from({ length: 5 }, (_, index) => (
                <div key={index} className="skeleton" style={{ height: 44 }} />
              ))}
            </div>
          </div>
        )}

        {status === 'error' && (
          <div className="state-block state-block--error" role="status">
            <h3>События недоступны</h3>
            <p>Досье дома не загрузилось, поэтому список событий не подменяется пустым.</p>
          </div>
        )}

        {status === 'success' && (
          events.length === 0 ? (
            <p className="search__message">
              В использованном источнике нет зафиксированных отключений за период. Это не
              доказывает их отсутствие.
            </p>
          ) : (
            <div className="events-layout">
              <div className="events-aside">
                <div role="group" aria-label="Фильтр событий" className="filter-row">
                  {FILTERS.map((option) => {
                    const selected = option === filter;
                    return (
                      <button
                        key={option}
                        type="button"
                        aria-pressed={selected}
                        data-cat={option === 'all' ? undefined : option}
                        onClick={() => selectFilter(option)}
                        className="filter-chip"
                      >
                        {option !== 'all' && <i aria-hidden="true" />}
                        {filterLabel(option)}
                      </button>
                    );
                  })}
                </div>
                <p className="t-small muted">
                  {filtered.length === 0
                    ? 'По этому фильтру записей нет.'
                    : `Показано ${Math.min(visible.length, filtered.length)} из ${filtered.length}.`}
                </p>
              </div>

              <div className="events-main">
                {filtered.length === 0 ? (
                  <p className="search__message">
                    В источнике не найдено записей этой категории за период.
                  </p>
                ) : (
                  <ul ref={listRef} aria-label="События дома" className="event-list">
                    {visible.map((event, index) => (
                      <li key={eventKey(event, index)} tabIndex={-1} className="event-item" data-cat={event.category}>
                        <span className="event-item__dot" aria-hidden="true" />
                        <div>
                          <p className="event-item__title">{categoryLabel(event.category)}</p>
                          <p className="event-item__time">
                            {formatDateTime(event.started_at)}
                            {' — '}
                            {event.ended_at === null ? 'Продолжается' : formatDateTime(event.ended_at)}
                          </p>
                          <a
                            href={event.source_url}
                            target="_blank"
                            rel="noopener noreferrer nofollow"
                            className="event-item__source"
                          >
                            Источник
                          </a>
                        </div>
                        <div className="event-item__side">
                          <div className="event-tags">
                            <span className="event-tag">
                              {event.kind === 'emergency' ? 'Аварийное' : 'Плановое'}
                            </span>
                            {event.is_mass && <span className="event-tag event-tag--accent">Массовое</span>}
                            {event.is_natural_disaster && (
                              <span className="event-tag event-tag--warn">Стихийное</span>
                            )}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}

                {visible.length < filtered.length && (
                  <button
                    ref={moreButtonRef}
                    type="button"
                    onClick={() => {
                      pendingFocusIndexRef.current = visibleCount;
                      setVisibleCount((count) => count + PAGE_SIZE);
                    }}
                    className="btn btn--secondary event-more"
                  >
                    Показать ещё
                  </button>
                )}
              </div>
            </div>
          )
        )}
      </div>
    </section>
  );
}
