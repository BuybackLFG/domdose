/** Ссылка «назад к поиску»: нужна и досье, и 404, поэтому живёт отдельно. */
import { ROUTES, interceptClick } from '../../lib/router'

export function BackToSearch() {
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
