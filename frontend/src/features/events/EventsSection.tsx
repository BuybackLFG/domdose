/**
 * Лента событий дома — таймлайн.
 *
 * Раздел F3 (DD-24). Заглушка: сортировка, бейджи, пустое состояние и
 * серьёзность без цвета — задача DD-24.
 */
import type { Event } from '../../types'

export function EventsSection({ events }: { events: Event[] }) {
  if (events.length === 0) return null
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-slate-300">События</h2>
      <ul className="space-y-1 text-sm text-slate-400">
        {events.map((event) => (
          <li key={event.id}>
            {event.date} — {event.title}
          </li>
        ))}
      </ul>
    </section>
  )
}
