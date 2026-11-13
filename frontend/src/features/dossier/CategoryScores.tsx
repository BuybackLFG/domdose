import { categoryLabel, formatScore } from './format';
import type { Loadable } from './useHouseDossier';
import type { HouseCategories, HouseDetailResponse } from './types';

interface CategoryScoresProps {
  detail: Loadable<HouseDetailResponse>;
}

const CATEGORY_ORDER: readonly (keyof HouseCategories)[] = [
  'electricity',
  'cold_water',
  'heating',
  'hot_water',
];

function Metrics({ values, title }: { values: HouseCategories[keyof HouseCategories]['metrics']; title: string }) {
  return (
    <dl aria-label={title} className="mt-3 grid grid-cols-3 gap-2 text-xs">
      <div>
        <dt className="text-text-secondary">Частота</dt>
        <dd className="mt-0.5 font-medium text-text">{values.frequency.toLocaleString('ru-RU')}</dd>
      </div>
      <div>
        <dt className="text-text-secondary">Часы</dt>
        <dd className="mt-0.5 font-medium text-text">{values.hours.toLocaleString('ru-RU')}</dd>
      </div>
      <div>
        <dt className="text-text-secondary">Максимум</dt>
        <dd className="mt-0.5 font-medium text-text">{values.longest.toLocaleString('ru-RU')}</dd>
      </div>
    </dl>
  );
}

export function CategoryScores({ detail }: CategoryScoresProps) {
  return (
    <section aria-labelledby="category-scores-heading" className="rounded-2xl bg-surface p-4 shadow-sm ring-1 ring-border sm:p-5">
      <h2 id="category-scores-heading" className="text-base font-semibold text-text">
        Оценки категорий
      </h2>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {CATEGORY_ORDER.map((category) => {
          if (detail.status !== 'success') {
            return (
              <article key={category} className="rounded-xl border border-border bg-surface-subtle p-3">
                <h3 className="text-sm font-semibold text-text">{categoryLabel(category)}</h3>
                <p className="mt-3 text-sm font-medium text-text-secondary">Нет исходных данных</p>
              </article>
            );
          }

          const categoryDetail = detail.data.categories[category];
          return (
            <article key={category} className="rounded-xl border border-border bg-surface-subtle p-3">
              <h3 className="text-sm font-semibold text-text">{categoryLabel(category)}</h3>
              <p className="mt-2 text-2xl font-semibold text-accent">
                {formatScore(categoryDetail.score)}
                <span className="ml-1 text-xs font-medium text-text-secondary">/ 100</span>
              </p>
              <Metrics values={categoryDetail.metrics} title={`Метрики: ${categoryLabel(category)}`} />
            </article>
          );
        })}
      </div>
    </section>
  );
}
