/** 404 приложения: адрес вне известных маршрутов. */
import { BackToSearch } from './BackToSearch'

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
