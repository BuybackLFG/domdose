/**
 * Дисклеймер досье — отдельный компонент, потому что текст принадлежит API.
 *
 * Здесь нельзя ничего дописывать «для ясности»: контракт требует, чтобы
 * пользователь увидел ровно `dossier.disclaimer`, а не нашу формулировку.
 */
export function Disclaimer({ text }: { text: string }) {
  return (
    <p
      role="note"
      className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2 text-xs text-slate-400"
    >
      {text}
    </p>
  )
}
