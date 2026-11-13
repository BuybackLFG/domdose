import { categoryLabel, formatDateTime } from './format';
import type { HouseDetailResponse } from './types';

interface HouseEventsProps {
  detail: HouseDetailResponse;
}

function eventKey(event: HouseDetailResponse['events'][number], index: number): string {
  return [
    event.house_id,
    event.category,
    event.started_at,
    event.ended_at ?? 'ongoing',
    event.source_url,
    index,
  ].join('|');
}

export function HouseEvents({ detail }: HouseEventsProps) {
  const events = [...detail.events].sort((left, right) => (
    Date.parse(right.started_at) - Date.parse(left.started_at)
  ));

  return (
    <section aria-labelledby="house-events-heading" className="rounded-2xl bg-surface p-4 shadow-sm ring-1 ring-border sm:p-5">
      <h2 id="house-events-heading" className="text-base font-semibold text-text">
        События дома
      </h2>

      {events.length === 0 ? (
        <p className="mt-3 rounded-xl bg-surface-subtle px-3 py-2 text-sm text-text-secondary">
          В использованном источнике нет зафиксированных отключений за указанное окно. Это не
          доказывает их отсутствие.
        </p>
      ) : (
        <ul aria-label="События дома" className="mt-3 space-y-2">
          {events.map((event, index) => (
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
    </section>
  );
}
