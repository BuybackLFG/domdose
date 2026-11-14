import { formatPeriod, formatScore, scoreBand } from './format';
import type { Loadable } from './useHouseDossier';
import type { HouseDetailResponse, HouseSummary as HouseSummaryDto } from './types';

interface HouseSummaryProps {
  house: HouseSummaryDto;
  district: string | null;
  detail: Loadable<HouseDetailResponse>;
  errorMessage: string | null;
  onRetryDetail: () => void;
}

const BAND_LABELS = {
  good: 'Надёжный диапазон выборки',
  mid: 'Средний диапазон выборки',
  bad: 'Слабое место выборки',
  none: 'Недостаточно записей',
} as const;

export function HouseSummary({
  house,
  district,
  detail,
  errorMessage,
  onRetryDetail,
}: HouseSummaryProps) {
  const score = detail.status === 'success' ? detail.data.overall_score : house.overall_score;
  const band = scoreBand(score);
  const period = detail.status === 'success' ? formatPeriod(detail.data.window) : null;
  const eventCount = detail.status === 'success' ? detail.data.event_count ?? detail.data.events.length : house.event_count;

  return (
    <section aria-labelledby="house-summary-heading" className="summary-panel">
      <p className="summary-panel__kicker">Сводка дома</p>
      <div>
        <h2 id="house-summary-heading" className="summary-panel__addr">
          {house.address}
        </h2>
        <p className="summary-panel__district">{district ?? 'Район не определён'}</p>
      </div>

      <div aria-live="polite">
        {detail.status === 'idle' || detail.status === 'loading' ? (
          <div className="state-block" role="status">
            <p className="loading-pulse">Загружаем досье…</p>
            <div aria-hidden="true" style={{ display: 'grid', gap: 8, width: '100%' }}>
              <div className="skeleton" style={{ height: 28, width: '70%' }} />
              <div className="skeleton" style={{ height: 14, width: '45%' }} />
            </div>
          </div>
        ) : detail.status === 'error' ? (
          <div className="state-block state-block--error" role="alert">
            <h3>{errorMessage}</h3>
            <p>Правдоподобный ноль не показывается: без исходных данных рейтинг отсутствует.</p>
            <button type="button" className="btn btn--secondary" onClick={onRetryDetail}>
              Повторить загрузку досье
            </button>
          </div>
        ) : (
          <>
            {detail.data.overall_score === null ? (
              <p className="score-note">
                <b>Нет данных для оценки</b>
                <span>Нет записей за период — данных для оценки недостаточно.</span>
              </p>
            ) : (
              <div className="score-block">
                <div
                  className="score-ring"
                  data-band={band}
                  style={{ '--pct': (detail.data.overall_score * 100).toFixed(1) } as React.CSSProperties}
                  aria-hidden="true"
                >
                  <p className="score-ring__text text-3xl">
                    <span className="score-ring__value">{formatScore(detail.data.overall_score)}</span>
                    <small className="score-ring__unit">/ 100</small>
                  </p>
                </div>
                <div className="score-note">
                  <b>{BAND_LABELS[band]}</b>
                </div>
              </div>
            )}

            <dl className="summary-rows" style={{ marginTop: 'var(--s-5)' }}>
              <div>
                <dt>Записей в источнике</dt>
                <dd>{eventCount ?? detail.data.events.length}</dd>
              </div>
              <div>
                <dt>Период</dt>
                <dd>{period}</dd>
              </div>
            </dl>
          </>
        )}
      </div>
    </section>
  );
}
