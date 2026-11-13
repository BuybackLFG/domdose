/**
 * Экран досье: общий каркас для трёх задач.
 *
 * Здесь только то, что не принадлежит ни F2, ни F3, ни F4: загрузка, 404,
 * ошибка сети и порядок разделов. Сами разделы живут в своих каталогах:
 * - `features/dossier/*` — паспорт, индекс, факты, источники (DD-23);
 * - `features/events/*` — лента событий (DD-24);
 * - `features/checklist/*` — чек-лист вопросов (DD-25).
 *
 * Поэтому параллельные ветки не конфликтуют в этом файле: каждая правит
 * только свои разделы.
 */
import { BackToSearch } from '../house/BackToSearch'
import { Disclaimer } from '../dossier/Disclaimer'
import { DossierHeader } from '../dossier/DossierHeader'
import { FactsSection } from '../dossier/FactsSection'
import { IndexPanel } from '../dossier/IndexPanel'
import { SourcesSection } from '../dossier/SourcesSection'
import { EventsSection } from '../events/EventsSection'
import { ChecklistSection } from '../checklist/ChecklistSection'
import { useDossier } from './useDossier'

function LoadingState() {
  return (
    <div aria-busy="true" aria-live="polite" className="space-y-4">
      <span className="sr-only">Загружаем досье дома</span>
      <div className="h-8 w-2/3 animate-pulse rounded-lg bg-slate-800/70" />
      <div className="h-4 w-1/3 animate-pulse rounded bg-slate-800/50" />
      <div className="h-40 animate-pulse rounded-xl border border-slate-800 bg-slate-900/40" />
    </div>
  )
}

function NotFoundState({ houseId }: { houseId: string }) {
  return (
    <div role="alert" className="space-y-2 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-6">
      <h1 className="text-2xl font-semibold text-slate-100">Досье не найдено</h1>
      <p className="text-sm text-slate-400">
        Дома <span className="font-mono break-all text-slate-300">{houseId}</span> нет в каталоге.
        Проверьте адрес или начните с поиска.
      </p>
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-rose-900/60 bg-rose-950/40 px-4 py-3 text-sm text-rose-200"
    >
      <span>Не удалось загрузить досье: {message}</span>
      <button
        type="button"
        onClick={onRetry}
        className="shrink-0 rounded-lg border border-rose-800 px-3 py-1.5 text-rose-100 hover:bg-rose-900/50"
      >
        Повторить
      </button>
    </div>
  )
}

export function HousePage({ houseId }: { houseId: string }) {
  const { status, dossier, error, retry } = useDossier(houseId)

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 px-4 py-10 sm:py-16">
      <BackToSearch />

      {status === 'loading' && <LoadingState />}
      {status === 'notFound' && <NotFoundState houseId={houseId} />}
      {status === 'error' && <ErrorState message={error ?? 'неизвестная ошибка'} onRetry={retry} />}

      {status === 'ready' && dossier && (
        <>
          <DossierHeader dossier={dossier} />
          {/* Дисклеймер обязателен по контракту и показывается дословно:
              это текст из API, а не наш. Вёрстку уточняет F2 (DD-23). */}
          <Disclaimer text={dossier.disclaimer} />
          <IndexPanel index={dossier.index ?? null} />
          <FactsSection facts={dossier.facts ?? []} />
          <EventsSection events={dossier.events ?? []} />
          <ChecklistSection houseId={dossier.house.id} items={dossier.checklist ?? []} />
          <SourcesSection sources={dossier.sources ?? []} />
        </>
      )}
    </main>
  )
}
