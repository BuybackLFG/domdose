import { formatAddressCount, formatScore, scoreBand } from './format';
import type { District } from './pilotHouses';
import type { HouseId, HouseSummary } from './types';

interface HouseListProps {
  houses: HouseSummary[];
  districts: Map<HouseId, District>;
  selectedHouseId: HouseId | null;
  onSelect: (houseId: HouseId) => void;
}

export function HouseList({ houses, districts, selectedHouseId, onSelect }: HouseListProps) {
  return (
    <section
      id="houses"
      className="section"
      data-screen="free"
      aria-labelledby="house-list-heading"
    >
      <div className="wrap">
        <div className="section-head">
          <h2 id="house-list-heading">Дома</h2>
          <p>{formatAddressCount(houses.length)}, включая дома без записей в источнике</p>
        </div>

        <ul className="house-grid" aria-label="Список адресов">
          {houses.map((house, index) => {
            const band = scoreBand(house.overall_score);
            return (
              <li key={house.house_id}>
                <button
                  type="button"
                  aria-pressed={selectedHouseId === house.house_id}
                  onClick={() => onSelect(house.house_id)}
                  className="house-row"
                >
                  <span aria-hidden="true" className="house-row__num">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span>
                    <span className="house-row__addr">{house.address}</span>
                    <span className="house-row__meta">
                      {districts.get(house.house_id) ?? 'Район не определён'} ·{' '}
                      {house.overall_score === null
                        ? 'Нет записей за период'
                        : `Индекс ${formatScore(house.overall_score)} / 100`}
                    </span>
                  </span>
                  <span className="house-row__score" data-band={band}>
                    {house.overall_score === null ? '—' : formatScore(house.overall_score)}
                    <small>{house.event_count ?? 0} зап.</small>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
