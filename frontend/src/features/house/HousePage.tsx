/**
 * Заглушка экрана досье: реальный экран — F2 (DD-23).
 *
 * Она существует уже сейчас, чтобы переход из поиска (AC «клик по варианту
 * открывает досье») было чем проверить, и чтобы роутер `/house/:id` не
 * появился задним числом в чужой задаче. Своих данных экран не берёт:
 * иначе фикстуры поиска утекут в прод-бандл.
 */
import { ROUTES, interceptClick } from '../../lib/router'

function BackToSearch() {
  return (
    <a
      href={ROUTES.search}
      onClick={(event) => interceptClick(event, ROUTES.search)}
      className="w-fit text-sm text-slate-400 underline-offset-4 hover:text-slate-200 hover:underline"
    >
      ← к поиску
    </a>
  )
}

export function HousePage({ houseId }: { houseId: string }) {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 px-4 py-10 sm:py-16">
      <BackToSearch />
      <header className="space-y-1">
        <h1 className="font-mono text-2xl font-semibold break-all text-slate-100">{houseId}</h1>
        <p className="text-sm text-slate-400">Досье дома</p>
      </header>
      <p className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-6 text-sm text-slate-400">
        Экран досье собирается в F2 (DD-23), данные — после B2/B3. Здесь пока только маршрут и
        проверка, что переход из поиска работает.
      </p>
    </main>
  )
}

export function NotFoundPage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 px-4 py-10 sm:py-16">
      <BackToSearch />
      <div role="alert" className="space-y-1">
        <h1 className="text-2xl font-semibold text-slate-100">Страница не найдена</h1>
        <p className="text-sm text-slate-400">
          Такого адреса в приложении нет. Начните с поиска — там весь каталог домов.
        </p>
      </div>
    </main>
  )
}
