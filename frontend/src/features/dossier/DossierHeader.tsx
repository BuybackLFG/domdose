/**
 * Шапка досье: адрес, район, паспортные признаки.
 *
 * Раздел F2 (DD-23). Пока здесь минимальная версия: она нужна, чтобы каркас
 * страницы собирался и другие разделы не зависели от ещё не написанного кода.
 */
import type { Dossier } from '../../types'

export function DossierHeader({ dossier }: { dossier: Dossier }) {
  const { house } = dossier
  return (
    <header className="space-y-1">
      <h1 className="text-2xl font-semibold tracking-tight text-slate-100 sm:text-3xl">
        {house.address}
      </h1>
      <p className="text-sm text-slate-400">
        {house.district} район
        {house.year ? ` · ${house.year} год` : ''}
        {house.floors ? ` · ${house.floors} этажей` : ''}
      </p>
    </header>
  )
}
