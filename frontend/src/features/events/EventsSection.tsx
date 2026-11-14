/**
 * Лента событий дома — таймлайн (DD-24, F3).
 *
 * Компонент только раскладывает данные: сортировку, подписи и разбор
 * необязательных полей делает `timeline.ts`, потому что именно там живут
 * ошибки, которые надо ловить тестами.
 *
 * Доступность: серьёзность и происхождение события подписаны словами, а не
 * только цветом. Цвет — украшение поверх текста: у части аудитории (и на
 * печати) он не читается.
 */
import { formatDate } from '../../lib/format'
import type { Event } from '../../types'

import { buildTimeline, type KindTone, type SeverityView, type TimelineItem } from './timeline'

/**
 * Цвет точки серьёзности. Смысл несёт подпись рядом, цвет — только акцент.
 * Ключи — уровни 1–3 из контракта; всё остальное падает в нейтральный вид.
 */
const SEVERITY_DOT: Record<number, string> = {
  1: 'bg-slate-400',
  2: 'bg-amber-400',
  3: 'bg-rose-500',
}

const SEVERITY_DOT_UNKNOWN = 'border border-slate-500 bg-transparent'

/** Левая полоса карточки — тот же акцент, что у точки. */
const SEVERITY_EDGE: Record<number, string> = {
  1: 'border-l-slate-600',
  2: 'border-l-amber-500',
  3: 'border-l-rose-600',
}

const SEVERITY_EDGE_UNKNOWN = 'border-l-slate-700'

/** Цвет бейджа происхождения. Подпись внутри бейджа важнее цвета. */
const KIND_BADGE: Record<KindTone, string> = {
  official: 'border-emerald-800/80 bg-emerald-950/50 text-emerald-200',
  ai: 'border-amber-800/80 bg-amber-950/40 text-amber-200',
  resident: 'border-sky-800/80 bg-sky-950/40 text-sky-200',
  unknown: 'border-slate-700 bg-slate-800/60 text-slate-300',
}

function SeverityMark({ severity }: { severity: SeverityView }) {
  const dot = SEVERITY_DOT[severity.level] ?? SEVERITY_DOT_UNKNOWN
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5 text-xs text-slate-300">
      <span aria-hidden="true" className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />
      <span>
        <span className="text-slate-400">серьёзность: </span>
        {severity.label}{' '}
        <span className="text-slate-500">({severity.scale})</span>
      </span>
    </span>
  )
}

function KindBadge({ item }: { item: TimelineItem }) {
  const tone = KIND_BADGE[item.kind.tone]
  return (
    <span className="inline-flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1">
      <span className={`rounded-full border px-2 py-0.5 text-xs ${tone}`}>{item.kind.label}</span>
      {item.kind.note && (
        <span className="text-xs text-slate-500">{item.kind.note}</span>
      )}
    </span>
  )
}

function EventRow({ item }: { item: TimelineItem }) {
  const edge = SEVERITY_EDGE[item.severity.level] ?? SEVERITY_EDGE_UNKNOWN
  return (
    <li
      // Цветная полоса слева — визуальный якорь таймлайна, не носитель смысла:
      // серьёзность рядом подписана словом.
      className={`rounded-xl border border-slate-800 border-l-2 bg-slate-900/50 p-4 sm:p-5 ${edge}`}
      data-kind={item.kind.tone}
      data-severity={item.severity.level}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <time
          {...(item.dateValid ? { dateTime: item.date } : {})}
          className="text-sm font-medium whitespace-nowrap text-slate-200"
        >
          {formatDate(item.date)}
        </time>
        <span className="rounded-md bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
          {item.typeLabel}
        </span>
        <SeverityMark severity={item.severity} />
      </div>

      <h3 className="mt-2 text-base font-semibold break-words text-slate-100">{item.title}</h3>

      {item.summary && (
        <p className="mt-1 text-sm break-words text-slate-400">{item.summary}</p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
        <KindBadge item={item} />
        {item.confidencePercent !== null && (
          <span
            className="text-slate-400"
            title="Уверенность источника ниже порога 80 %: событие не попадает в индекс"
          >
            уверенность: {item.confidencePercent} %
          </span>
        )}
        {item.district && <span className="text-slate-400">район: {item.district}</span>}
        <a
          href={item.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-slate-300 underline underline-offset-4 hover:text-emerald-300"
        >
          {item.sourceHost ? `Источник: ${item.sourceHost}` : 'Источник'}
          <span className="sr-only"> (откроется в новой вкладке)</span>
        </a>
      </div>
    </li>
  )
}

function EmptyEvents() {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-6 text-center">
      <p className="text-sm font-medium text-slate-300">Событий не найдено</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
        В доступных данных нет записей о событиях по этому дому. Это не доказывает,
        что отключений или других событий не было.
      </p>
    </div>
  )
}

export function EventsSection({ events }: { events: Event[] }) {
  const items = buildTimeline(events)

  return (
    <section aria-labelledby="events-heading" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id="events-heading" className="text-sm font-semibold text-slate-300">
          События
        </h2>
        {items.length > 0 && <p className="text-xs text-slate-500">сначала новые</p>}
      </div>

      {items.length === 0 ? (
        <EmptyEvents />
      ) : (
        <ol className="space-y-3">
          {items.map((item) => (
            <EventRow key={item.id} item={item} />
          ))}
        </ol>
      )}
    </section>
  )
}
