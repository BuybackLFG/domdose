import { scoreBand, type ScoreBand } from './format';
import type { Loadable } from './useHouseDossier';
import type { HouseId, HouseListResponse } from './types';

interface SampleOverviewProps {
  list: Loadable<HouseListResponse>;
  selectedHouseId: HouseId | null;
}

const BAND_LABEL: Record<ScoreBand, string> = {
  good: '90 и выше',
  mid: '75–90',
  bad: 'ниже 75',
  none: 'нет записей',
};

export function SampleOverview({ list, selectedHouseId }: SampleOverviewProps) {
  const houses = list.status === 'success' ? list.data.houses : [];
  const withRecords = houses.filter((house) => (house.event_count ?? 0) > 0).length;
  const totalEvents = houses.reduce((sum, house) => sum + (house.event_count ?? 0), 0);
  const maxEvents = Math.max(1, ...houses.map((house) => house.event_count ?? 0));

  return (
    <section id="sample" aria-labelledby="sample-heading" className="section" data-screen="free">
      <div className="wrap">
        <div className="section-head">
          <h2 id="sample-heading">Выборка из 20 домов</h2>
          <p>
            За 30 дней в выборке {houses.length === 0 ? '—' : totalEvents} записей об отключениях.
            Высота столбика — число записей у дома, цвет — его индекс.
          </p>
        </div>

        <dl className="sample-stats">
          <div className="sample-stat">
            <dt>Домов в выборке</dt>
            <dd>{houses.length === 0 ? '—' : houses.length}</dd>
          </div>
          <div className="sample-stat">
            <dt>Домов с записями</dt>
            <dd>{houses.length === 0 ? '—' : withRecords}</dd>
          </div>
          <div className="sample-stat">
            <dt>Записей за период</dt>
            <dd>{houses.length === 0 ? '—' : totalEvents}</dd>
          </div>
          <div className="sample-stat">
            <dt>Домов без записей</dt>
            <dd>{houses.length === 0 ? '—' : houses.length - withRecords}</dd>
          </div>
        </dl>

        <div className="sample-plot">
          <p className="sample-axis-label sample-axis-label--y">Записей</p>
          <div className="sample-plot__body">
            <div
              className="sample-chart"
              role="img"
              aria-label={`Число записей у каждого из ${houses.length || 20} домов: от 0 до ${maxEvents}`}
            >
              {houses.length === 0
                ? Array.from({ length: 20 }, (_, index) => (
                  <span key={index} className="sample-bar" data-band="none">
                    <span className="sample-bar__fill" style={{ '--bar': '2%' } as React.CSSProperties} />
                  </span>
                ))
                : houses.map((house) => {
                  const count = house.event_count ?? 0;
                  const band = scoreBand(house.overall_score);
                  return (
                    <span
                      key={house.house_id}
                      className="sample-bar"
                      data-band={band}
                      data-selected={house.house_id === selectedHouseId}
                      title={`${house.address}: ${count} записей`}
                      style={{ '--bar': `${Math.max(2, (count / maxEvents) * 100)}%` } as React.CSSProperties}
                    >
                      <span className="sample-bar__fill" />
                    </span>
                  );
                })}
            </div>

            <div className="sample-axis" aria-hidden="true">
              <span>1</span>
              <span>5</span>
              <span>10</span>
              <span>15</span>
              <span>20</span>
            </div>
          </div>
        </div>
        <p className="sample-axis-label sample-axis-label--x">Дома выборки</p>

        <div className="sample-legend" aria-label="Цвет столбика">
          {(['good', 'mid', 'bad', 'none'] as const).map((band) => (
            <span key={band}>
              <i data-band={band} aria-hidden="true" />
              Индекс {BAND_LABEL[band]}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
