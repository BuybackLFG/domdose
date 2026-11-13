/**
 * Шапка досье: адрес и паспортные признаки дома (раздел F2, DD-23).
 *
 * Правило: `null` — это «нет данных», и показывать вместо него ноль, прочерк
 * или «неизвестно» нельзя. Отсутствующее поле просто не попадает в список.
 * `avariy` и `caprepair` — обязательные boolean, поэтому бейдж рисуем только
 * когда флаг истинный: отсутствие бейджа читается как «не отмечено», а не как
 * «дом точно в порядке».
 */
import type { Dossier } from '../../types'

interface PassportRow {
  term: string
  value: string
}

function passportRows(dossier: Dossier): PassportRow[] {
  const { house } = dossier
  const rows: PassportRow[] = []

  if (house.year !== null && house.year !== undefined) {
    rows.push({ term: 'Год постройки', value: `${house.year}` })
  }
  if (house.floors !== null && house.floors !== undefined) {
    rows.push({ term: 'Этажность', value: `${house.floors}` })
  }
  if (house.material !== null && house.material !== undefined) {
    rows.push({ term: 'Материал стен', value: house.material })
  }
  if (house.uk !== null && house.uk !== undefined) {
    rows.push({ term: 'Управляющая компания', value: house.uk })
  }
  // `wear_pct` — уже проценты по ГИС ЖКХ, а не доля, поэтому `formatWeight`
  // здесь не годится: он умножал бы на 100 второй раз.
  if (house.wear_pct !== null && house.wear_pct !== undefined) {
    rows.push({ term: 'Износ', value: `${house.wear_pct} %` })
  }

  return rows
}

export function DossierHeader({ dossier }: { dossier: Dossier }) {
  const { house } = dossier

  return (
    <header className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight break-words text-slate-100 sm:text-3xl">
          {house.address}
        </h1>
        <p className="text-sm text-slate-400">
          {house.district} район
          {house.year !== null && house.year !== undefined ? ` · ${house.year} год` : ''}
        </p>
      </div>

      {(house.avariy || house.caprepair) && (
        <ul className="flex flex-wrap gap-2" aria-label="Статус дома">
          {house.avariy && (
            <li className="rounded-md border border-rose-900/60 bg-rose-950/40 px-2 py-0.5 text-xs font-medium text-rose-200">
              аварийный
            </li>
          )}
          {house.caprepair && (
            <li className="rounded-md border border-amber-900/60 bg-amber-950/40 px-2 py-0.5 text-xs font-medium text-amber-200">
              в плане капремонта
            </li>
          )}
        </ul>
      )}

      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
        {passportRows(dossier).map((row) => (
          <div key={row.term} className="flex min-w-0 flex-wrap gap-x-2">
            <dt className="text-slate-500">{row.term}</dt>
            <dd className="min-w-0 break-words text-slate-200">{row.value}</dd>
          </div>
        ))}
      </dl>
    </header>
  )
}
