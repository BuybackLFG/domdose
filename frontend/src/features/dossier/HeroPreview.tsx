import { categoryLabel, formatDay, formatPeriod, formatScore, scoreBand } from './format';
import type { Loadable } from './useHouseDossier';
import type { HouseCategories, HouseDetailResponse, HouseSummary } from './types';

interface HeroPreviewProps {
  listStatus: 'idle' | 'loading' | 'success' | 'error';
  selectedHouse: HouseSummary | null;
  district: string | null;
  detail: Loadable<HouseDetailResponse>;
}

const CATEGORY_ORDER: readonly (keyof HouseCategories)[] = [
  'electricity',
  'cold_water',
  'heating',
  'hot_water',
];

export function HeroPreview({ listStatus, selectedHouse, district, detail }: HeroPreviewProps) {
  const score = detail.status === 'success' ? detail.data.overall_score : selectedHouse?.overall_score ?? null;
  const period = detail.status === 'success' ? formatPeriod(detail.data.window) : null;
  const events = detail.status === 'success' ? detail.data.events : [];
  const loading = detail.status === 'idle' || detail.status === 'loading';
  const eventCount = detail.status === 'success' ? detail.data.event_count ?? events.length : 0;
  const filledCategories = detail.status === 'success'
    ? CATEGORY_ORDER.filter((category) => detail.data.categories[category] !== null).length
    : 0;

  return (
    <div className="dossier-window" aria-label="Предпросмотр досье">
      <div className="dossier-window__bar" aria-hidden="true">
        <span className="dossier-window__dots"><span /><span /><span /></span>
        <span className="dossier-window__title">ДомДосье</span>
      </div>

      <div className="dossier-window__body">
        <div className="dossier-window__head">
          <div>
            <p className="dossier-window__addr">
              {selectedHouse?.address
                ?? (listStatus === 'error' ? 'Выборка недоступна' : 'Загружаем выборку…')}
            </p>
            <p className="dossier-window__district">
              {district ?? (listStatus === 'error' ? 'Нет связи с API' : 'Владивосток')}
            </p>
          </div>
          <div className="dossier-window__score">
            <b>{score === null ? '—' : formatScore(score)}</b>
            <span>{score === null ? 'нет данных' : '/ 100'}</span>
          </div>
        </div>

        {detail.status === 'success' ? (
          <>
            <div className="dossier-window__cats">
              {CATEGORY_ORDER.map((category) => {
                const categoryDetail = detail.data.categories[category];
                const value = categoryDetail?.score ?? 0;
                return (
                  <div
                    key={category}
                    className="win-cat"
                    data-band={categoryDetail ? scoreBand(categoryDetail.score) : 'none'}
                  >
                    <div className="win-cat__head">
                      <span>{categoryLabel(category)}</span>
                      <b>{categoryDetail === null ? '—' : formatScore(categoryDetail.score)}</b>
                    </div>
                    <span className="win-cat__track" aria-hidden="true">
                      <span className="win-cat__fill" style={{ width: `${value * 100}%` }} />
                    </span>
                  </div>
                );
              })}
            </div>

            <dl className="dossier-window__facts">
              <div>
                <dt>Записей</dt>
                <dd>{eventCount}</dd>
              </div>
              <div>
                <dt>Категорий</dt>
                <dd>{filledCategories} из 4</dd>
              </div>
              <div>
                <dt>Полнота</dt>
                <dd>неизвестна</dd>
              </div>
            </dl>

            <div className="dossier-window__events">
              {events.slice(0, 4).map((event) => (
                <div key={`${event.category}-${event.started_at}-${event.source_url}`} className="win-event">
                  <span className="win-event__dot" data-cat={event.category} aria-hidden="true" />
                  <span>{categoryLabel(event.category)}</span>
                  <span className="win-event__date">{formatDay(event.started_at)}</span>
                </div>
              ))}
              {events.length === 0 && (
                <div className="win-event">
                  <span className="win-event__dot" aria-hidden="true" />
                  <span>Записей об отключениях нет</span>
                  <span className="win-event__date">—</span>
                </div>
              )}
            </div>

            <a className="link dossier-window__more" href="#events">Все события</a>

            <div className="dossier-window__foot">
              <span>{period}</span>
              <span>{eventCount} записей</span>
            </div>
          </>
        ) : loading ? (
          <div className="dossier-window__pending" aria-hidden="true">
            <div className="skeleton" style={{ height: 54 }} />
            <div className="skeleton" style={{ height: 54 }} />
            <div className="skeleton" style={{ height: 54 }} />
          </div>
        ) : (
          <div className="state-block state-block--error dossier-window__error">
            <h3>Досье не загрузилось</h3>
            <p>Данные не подменяются нулём: рейтинг отсутствует до ответа источника.</p>
          </div>
        )}

        {detail.status !== 'success' && (
          <div className="dossier-window__foot">
            <span>Публичные объявления</span>
            <span>30 дней</span>
          </div>
        )}
      </div>
    </div>
  );
}
