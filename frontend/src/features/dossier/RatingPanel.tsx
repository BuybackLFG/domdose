import { formatDate } from '../../lib/format'
import type { Dossier } from '../../types'

type Rating = NonNullable<Dossier['rating']>

const LABELS: Record<string, string> = {
  electricity: 'Электричество', cold_water: 'Холодная вода',
  heating: 'Отопление', hot_water: 'Горячая вода',
}
const REASONS: Record<string, string> = {
  UNKNOWN_SERVICE: 'Нет подтверждённых данных об услуге.',
  NOT_APPLICABLE: 'Оценка для этой услуги неприменима.',
  HEATING_SEASON_UNKNOWN: 'Неизвестны границы отопительного сезона.',
  AMBIGUOUS_MATCH: 'Привязка события к дому неоднозначна.',
  UNKNOWN_OVERLAP: 'Неизвестно, попадает ли событие в окно расчёта.',
  UNKNOWN_KIND: 'Неизвестен тип отключения.',
  UNKNOWN_DURATION: 'Неизвестна продолжительность отключения.',
  BASELINE_INCONSISTENT: 'Сравнение со средним по городу невозможно из-за противоречия данных.',
  BASELINE_UNAVAILABLE: 'Нет данных для сравнения со средним по городу.',
  UNKNOWN_AFFECTED_COUNT: 'Неизвестно число затронутых домов.',
}
const label = (type: string) => LABELS[type] ?? type
const interval = (start: string, end: string) => `${formatDate(start)} — ${formatDate(end)}`
const number = (value: number) => new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)

export function RatingPanel({ rating }: { rating: Rating }) {
  const house = rating.houses[0]
  return (
    <section aria-labelledby="rating-title" className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      <h2 id="rating-title" className="text-sm font-semibold text-slate-300">Оценка отключений</h2>
      <p className="text-sm text-slate-300">
        {house?.overall == null ? 'Общая оценка недоступна.' : `Приблизительная оценка: ${number(house.overall * 100)} из 100.`}
      </p>
      <p className="text-xs text-slate-400">
        Окно расчёта: с {formatDate(rating.window.start.slice(0, 10))} до {formatDate(rating.window.end_exclusive.slice(0, 10))} (конечная дата не включена).
        Оценка основана только на наблюдаемых публикациях и не описывает все отключения.
      </p>
      {house && <ul className="grid gap-3 sm:grid-cols-2">
        {house.categories.map((category) => <li key={category.type} className="space-y-1 rounded-lg border border-slate-800 p-3 text-sm">
          <h3 className="font-medium text-slate-200">{label(category.type)}</h3>
          <p className="text-slate-300">{category.score == null ? 'Оценка недоступна' : `Приблизительно ${number(category.score * 100)} из 100`}</p>
          {category.reason && <p className="text-xs text-slate-400">{REASONS[category.reason] ?? `Причина: ${category.reason}`}</p>}
          {category.metrics.maximum != null && <p className="text-xs text-slate-400">Наибольшая взвешенная продолжительность: {number(category.metrics.maximum)} ч. Вес учитывает тип отключения, поэтому это не обязательно фактическая длительность.</p>}
        </li>)}
      </ul>}
      <div className="space-y-2 border-t border-slate-800 pt-3 text-xs text-slate-400">
        <h3 className="font-semibold text-slate-300">Покрытие источников</h3>
        {rating.source_spans.length === 0 ? <p>Сведения о покрытии отсутствуют.</p> : <ul className="space-y-1">
          {rating.source_spans.map((span) => <li key={span.type}>
            <span className="text-slate-300">{label(span.type)}:</span>{' '}
            {span.intervals.length ? span.intervals.map((item) => interval(item.start, item.end)).join('; ') : 'периоды покрытия не указаны'}.
            {span.gaps.length > 0 && ` Пробелы: ${span.gaps.map((item) => interval(item.start, item.end)).join('; ')}.`}
            {span.unknown_source_ids.length > 0 && ' Для части источников покрытие неизвестно.'}
          </li>)}
        </ul>}
      </div>
      {rating.limitations.length > 0 && <details className="text-xs leading-relaxed text-slate-400">
        <summary className="cursor-pointer text-slate-300">Ограничения данных ({rating.limitations.length})</summary>
        <ul className="mt-2 list-disc space-y-1 pl-4">{rating.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>
      </details>}
    </section>
  )
}
