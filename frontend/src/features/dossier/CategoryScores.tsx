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

const METRIC_NOTES: readonly string[] = [
  'Частота — сколько раз отключали за 30 дней. Аварийное отключение считается за 1, плановое — за 0,4; массовое или стихийное — вдвое меньше.',
  'Часы — суммарная длительность отключений за 30 дней с теми же весами.',
  'Максимум — самое долгое отдельное отключение с теми же весами, в часах.',
  'Оценка категории: 100 — не хуже среднего по всем домам; чем сильнее дом превышает среднее, тем ниже оценка.',
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

/**
 * Тело карточки по состоянию досье: загрузка, отказ или оценка.
 * «Нет исходных данных» — только при отказе no_data, не во время загрузки.
 */
function CategoryBody({ detail, category }: CategoryScoresProps & { category: keyof HouseCategories }) {
  switch (detail.status) {
    case 'idle':
    case 'loading':
      return <div aria-hidden="true" className="loading-pulse mt-3 h-14 rounded-lg bg-border/60" />;
    case 'error':
      return (
        <p className="mt-3 text-sm font-medium text-text-secondary">
          {detail.error.kind === 'no_data' ? 'Нет исходных данных' : 'Оценка недоступна'}
        </p>
      );
    case 'success': {
      const categoryDetail = detail.data.categories[category];
      return (
        <>
          <p className="mt-2 text-2xl font-semibold text-accent">
            {formatScore(categoryDetail.score)}
            <span className="ml-1 text-xs font-medium text-text-secondary">/ 100</span>
          </p>
          <Metrics values={categoryDetail.metrics} title={`Метрики: ${categoryLabel(category)}`} />
        </>
      );
    }
  }
}

export function CategoryScores({ detail }: CategoryScoresProps) {
  const pending = detail.status === 'idle' || detail.status === 'loading';

  return (
    <section
      aria-labelledby="category-scores-heading"
      aria-busy={pending}
      className="rounded-2xl bg-surface p-4 shadow-sm ring-1 ring-border sm:p-5"
    >
      <h2 id="category-scores-heading" className="text-base font-semibold text-text">
        Оценки категорий
      </h2>
      {pending && (
        <p role="status" className="loading-pulse mt-1 text-sm text-text-secondary">
          Загружаем оценки категорий…
        </p>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {CATEGORY_ORDER.map((category) => (
          <article key={category} className="rounded-xl border border-border bg-surface-subtle p-3">
            <h3 className="text-sm font-semibold text-text">{categoryLabel(category)}</h3>
            <CategoryBody detail={detail} category={category} />
          </article>
        ))}
      </div>

      <div className="mt-4 space-y-1 text-xs leading-5 text-text-secondary">
        {METRIC_NOTES.map((note) => (
          <p key={note}>{note}</p>
        ))}
      </div>
    </section>
  );
}
