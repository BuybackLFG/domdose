import { useMemo } from 'react';
import { CategoryScores } from './CategoryScores';
import { HeroPreview } from './HeroPreview';
import { HouseEvents } from './HouseEvents';
import { HouseList } from './HouseList';
import { HouseMap } from './HouseMap';
import { HouseSearch } from './HouseSearch';
import { HouseSummary } from './HouseSummary';
import { PILOT_HOUSES } from './pilotHouses';
import { SampleOverview } from './SampleOverview';
import { formatScore, scoreBand } from './format';
import { useHouseDossier } from './useHouseDossier';

const HEADER_NOTE = 'Приближённые данные по публичным объявлениям об отключениях. '
  + 'Дома сравниваются между собой, а не со всем Владивостоком.';

function detailStatus(status: 'idle' | 'loading' | 'success' | 'error') {
  if (status === 'success') return 'success' as const;
  if (status === 'error') return 'error' as const;
  return 'loading' as const;
}

export function DossierPage() {
  const {
    list,
    listErrorMessage,
    selectedHouse,
    selectedHouseId,
    detail,
    detailErrorMessage,
    query,
    search,
    selectHouse,
    updateQuery,
    moveSearchActive,
    submitSearch,
    retryList,
    retryDetail,
  } = useHouseDossier();

  const districts = useMemo(
    () => new Map(PILOT_HOUSES.map((house) => [house.house_id, house.district] as const)),
    [],
  );

  const houses = useMemo(() => (list.status === 'success' ? list.data.houses : []), [list]);
  const band = scoreBand(selectedHouse?.overall_score ?? null);
  const events = detail.status === 'success' ? detail.data.events : [];

  return (
    <div className="page">
      <a href="#dossier" className="skip-link">Перейти к досье дома</a>

      <header className="nav">
        <div className="nav__bar wrap">
          <a className="nav__logo" href="#top" aria-label="ДомДосье — к началу страницы">
            <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">
              <rect width="32" height="32" rx="8" fill="currentColor" />
              <path
                d="M8 15.5 16 8l8 7.5M10.5 15v9h11v-9M13 20.5h2.2l1.2-2.6 1.4 4.4 1.2-1.8h1"
                fill="none"
                stroke="var(--bg)"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            ДомДосье
          </a>
          <nav id="site-nav" className="nav__links" aria-label="Разделы страницы">
            <a className="nav__link" href="#sample">Выборка</a>
            <a className="nav__link" href="#map">Карта</a>
            <a className="nav__link" href="#houses">Дома</a>
            <a className="nav__link" href="#events">События</a>
          </nav>
          <div className="nav__actions">
            <a className="btn btn--primary btn--sm" href="#top">Найти дом</a>
          </div>
          <button
            className="nav__toggle"
            type="button"
            aria-label="Меню"
            aria-expanded="false"
            aria-controls="site-nav"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <path d="M2 5h14M2 13h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        </div>
      </header>

      <main id="top">
        <section className="hero hero--split" aria-labelledby="page-heading">
          <div className="wrap">
            <div className="hero-text hero__grid grid">
              <div className="hero__text hero__copy">
                <p className="hero__kicker">
                  <span className="dot" aria-hidden="true" />
                  Владивосток · 20 домов · 30 дней
                </p>
                <h1 id="page-heading">Коммунальная надёжность домов</h1>
                <p className="hero__lead">{HEADER_NOTE}</p>

                <div id="search">
                  <HouseSearch
                    query={query}
                    search={search}
                    onQueryChange={updateQuery}
                    onMoveActive={moveSearchActive}
                    onSubmit={submitSearch}
                    onSelect={selectHouse}
                  />
                </div>
              </div>

              <div className="hero__media">
                <HeroPreview
                  listStatus={list.status}
                  selectedHouse={selectedHouse}
                  district={selectedHouse ? districts.get(selectedHouse.house_id) ?? null : null}
                  detail={detail}
                />
              </div>
            </div>
          </div>
        </section>

        <SampleOverview list={list} selectedHouseId={selectedHouseId} />

        <section id="map" className="section" data-screen="free" aria-labelledby="map-heading">
          <div className="wrap">
            <div className="section-head">
              <h2 id="map-heading">Карта домов</h2>
              <p>
                Все адреса выборки на локальной подложке. Цвет точки — индекс дома, размер — выбор.
                Карта не обращается к внешним тайлам и геосервисам.
              </p>
            </div>

            {list.status === 'error' ? (
              <div className="state-block state-block--error" role="alert">
                <h3>{listErrorMessage}</h3>
                <p>Карта не подменяется пустым кадром: список домов недоступен.</p>
                <button type="button" className="btn btn--secondary" onClick={retryList}>
                  Повторить загрузку
                </button>
              </div>
            ) : (
              <div className="map-shell">
                <HouseMap
                  houses={houses}
                  selectedHouseId={selectedHouseId}
                  onSelectHouse={selectHouse}
                />

                <div className="map-legend" aria-label="Индекс дома на карте">
                  <span><i data-band="good" aria-hidden="true" />90 и выше</span>
                  <span><i data-band="mid" aria-hidden="true" />75–90</span>
                  <span><i data-band="bad" aria-hidden="true" />ниже 75</span>
                  <span><i data-band="none" aria-hidden="true" />нет записей</span>
                </div>

                {selectedHouse && (
                  <div className="map-card">
                    <div className="map-card__top">
                      <div>
                        <p className="map-card__addr">{selectedHouse.address}</p>
                        <p className="map-card__meta">
                          {districts.get(selectedHouse.house_id) ?? 'Район не определён'} ·{' '}
                          {selectedHouse.event_count ?? 0} записей
                        </p>
                      </div>
                      <p className="map-card__score" data-band={band}>
                        <b>{selectedHouse.overall_score === null ? '—' : formatScore(selectedHouse.overall_score)}</b>
                        <span>/ 100</span>
                      </p>
                    </div>
                    <div className="map-card__foot">
                      <a className="link" href="#dossier">Открыть досье</a>
                      <a className="link" href="#events">События дома</a>
                    </div>
                  </div>
                )}

              </div>
            )}

            {list.status === 'loading' && (
              <p role="status" className="loading-pulse t-small muted" style={{ marginTop: 'var(--s-4)' }}>
                Загружаем дома…
              </p>
            )}
          </div>
        </section>

        <section id="dossier" className="section" data-screen="free" aria-labelledby="dossier-heading">
          <div className="wrap">
            <div className="section-head">
              <h2 id="dossier-heading">Досье выбранного дома</h2>
            </div>

            {list.status === 'loading' && (
              <div className="state-block" role="status">
                <p className="loading-pulse">Загружаем дома…</p>
              </div>
            )}

            {list.status === 'success' && selectedHouse && (
              <div className="dossier-grid">
                <HouseSummary
                  house={selectedHouse}
                  district={districts.get(selectedHouse.house_id) ?? null}
                  detail={detail}
                  errorMessage={detailErrorMessage}
                  onRetryDetail={retryDetail}
                />
                <CategoryScores detail={detail} />
              </div>
            )}
          </div>
        </section>

        {list.status === 'success' && (
          <HouseList
            houses={houses}
            districts={districts}
            selectedHouseId={selectedHouseId}
            onSelect={selectHouse}
          />
        )}

        {list.status === 'success' && selectedHouse && (
          <HouseEvents
            key={`${selectedHouse.house_id}-${detail.status === 'success' ? detail.data.house_id : 'pending'}`}
            events={events}
            status={detailStatus(detail.status)}
          />
        )}
      </main>

      <footer className="footer closing">
        <div className="wrap">
          <div className="closing__cta">
            <div className="section-head">
              <h2>Проверьте дом до сделки</h2>
              <p>
                Введите адрес и посмотрите отключения за 30 дней, оценки категорий и худшую
                категорию дома. Сравнение идёт только между домами выборки.
              </p>
            </div>
            <div className="btn-row">
              <a className="btn btn--primary" href="#top">Найти дом</a>
              <a className="btn btn--secondary" href="#houses">Все дома</a>
            </div>
          </div>

          <div className="closing__links">
            <div className="footer__grid">
              <div>
                <p className="footer__mark">ДомДосье</p>
                <p className="footer__lede">
                  Коммунальное досье дома во Владивостоке: отключения воды, электричества и
                  отопления за 30 дней, собранные из публичных объявлений.
                </p>
              </div>
              <div className="footer__col">
                <h3>Данные</h3>
                <ul>
                  <li>Публичные объявления об отключениях</li>
                  <li>20 домов в пяти районах</li>
                  <li>Окно — 30 дней</li>
                  <li>Полнота журнала неизвестна</li>
                </ul>
              </div>
              <div className="footer__col">
                <h3>Ограничения</h3>
                <ul>
                  <li>Набор приближённый, а не городская статистика</li>
                  <li>Пустой список не доказывает отсутствие отключений</li>
                  <li>Рейтинг не заменяет проверку дома</li>
                  <li>
                    Категории без записей входят в расчёт индекса и среднего с нулевыми
                    показателями; это не подтверждает надёжность дома
                  </li>
                </ul>
              </div>
              <div className="footer__col">
                <h3>Разделы</h3>
                <ul>
                  <li><a href="#sample">Выборка</a></li>
                  <li><a href="#map">Карта</a></li>
                  <li><a href="#dossier">Досье</a></li>
                  <li><a href="#houses">Дома</a></li>
                  <li><a href="#events">События</a></li>
                </ul>
              </div>
            </div>
            <p className="footer__legal">
              <span>ДомДосье · Владивосток</span>
              <span>Данные приближённые: проверяйте дом отдельно</span>
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
