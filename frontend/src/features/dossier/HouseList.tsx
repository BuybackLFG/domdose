import { formatAddressCount, formatScore } from './format';
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
    <section aria-labelledby="house-list-heading" className="rounded-2xl bg-surface p-4 shadow-sm ring-1 ring-border sm:p-5">
      <h2 id="house-list-heading" className="text-base font-semibold text-text">
        Дома
      </h2>
      <p className="mt-1 text-sm text-text-secondary">
        {formatAddressCount(houses.length)}, включая дома без отключений
      </p>

      <ul className="mt-4 grid gap-2 lg:grid-cols-2" aria-label="Список адресов">
        {houses.map((house) => (
          <li key={house.house_id}>
            <button
              type="button"
              aria-pressed={selectedHouseId === house.house_id}
              onClick={() => onSelect(house.house_id)}
              className={`min-h-14 w-full rounded-xl border px-3 py-2 text-left transition ${
                selectedHouseId === house.house_id
                  ? 'border-accent bg-accent-soft text-text'
                  : 'border-border bg-surface text-text hover:border-accent hover:bg-surface-subtle'
              }`}
            >
              <span className="block text-sm font-medium leading-5">{house.address}</span>
              <span className="mt-1 block text-xs text-text-secondary">
                {districts.get(house.house_id) ?? 'Район не определён'} · Рейтинг {formatScore(house.overall_score)} / 100
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
