import { formatDateTime, formatScore } from './format';
import type { Loadable } from './useHouseDossier';
import type { HouseDetailResponse, HouseSummary as HouseSummaryDto } from './types';

interface HouseSummaryProps {
  house: HouseSummaryDto;
  district: string | null;
  detail: Loadable<HouseDetailResponse>;
  errorMessage: string | null;
  onRetryDetail: () => void;
}

export function HouseSummary({ house, district, detail, errorMessage, onRetryDetail }: HouseSummaryProps) {
  return (
    <section aria-labelledby="house-summary-heading" className="rounded-2xl bg-surface p-4 shadow-sm ring-1 ring-border sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">Сводка дома</p>
          <h2 id="house-summary-heading" className="mt-1 text-lg font-semibold leading-7 text-text">
            {house.address}
          </h2>
          <p className="mt-1 text-sm text-text-secondary">
            {district ?? 'Район не определён'}
          </p>
        </div>
      </div>

      <div className="mt-4" aria-live="polite">
        {detail.status === 'loading' && (
          <div role="status" className="rounded-xl bg-surface-subtle p-4">
            <p className="loading-pulse text-sm font-medium text-text-secondary">Загружаем досье…</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-4" aria-hidden="true">
              {Array.from({ length: 4 }, (_, index) => (
                <div key={index} className="h-20 rounded-xl bg-border/60" />
              ))}
            </div>
          </div>
        )}

        {detail.status === 'success' && (
          <div className="rounded-xl bg-accent-soft p-4">
            <p className="text-sm text-text-secondary">Общий рейтинг</p>
            <p className="mt-1 text-3xl font-semibold text-accent">
              {formatScore(detail.data.overall_score)}
              <span className="ml-1 text-base font-medium text-text-secondary">/ 100</span>
            </p>
            <p className="mt-2 text-sm text-text-secondary">
              Окно расчёта: [{formatDateTime(detail.data.window.start)};{' '}
              {formatDateTime(detail.data.window.end)}), UTC+10
            </p>
          </div>
        )}

        {detail.status === 'error' && (
          <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 p-4">
            <p className="text-sm font-medium text-text">{errorMessage}</p>
            <p className="mt-1 text-sm text-text-secondary">
              Правдоподобный ноль не показывается: без исходных данных рейтинг отсутствует.
            </p>
            <button
              type="button"
              onClick={onRetryDetail}
              className="mt-3 min-h-11 rounded-xl bg-accent px-4 text-sm font-medium text-white transition hover:bg-accent-hover"
            >
              Повторить загрузку досье
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
