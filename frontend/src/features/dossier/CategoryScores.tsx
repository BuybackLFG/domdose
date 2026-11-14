import { categoryLabel, formatScore } from './format';
import type { Loadable } from './useHouseDossier';
import type { HouseCategories, HouseDetailResponse, MetricValues } from './types';
import { WeakestCategory } from './WeakestCategory';

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
  'Частота — сколько раз отключали за 30 дней. Аварийное отключение считается за 1, '
    + 'плановое — за 0,4; массовое или стихийное — вдвое меньше.',
  'Часы — суммарная длительность отключений за 30 дней с теми же весами.',
  'Максимум — наибольшая длительность одного отключения после умножения на его вес, в часах.',
  'Оценки рассчитаны по найденным записям и сравнению с выбранными домами. Полнота журнала неизвестна.',
];

function formatMetric(value: number): string {
  return value.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
}

function Metrics({ values, title }: { values: MetricValues; title: string }) {
  return (
    <dl aria-label={title} className="category-card__metrics">
      <div>
        <dt>Частота</dt>
        <dd>{formatMetric(values.frequency)}</dd>
      </div>
      <div>
        <dt>Часы</dt>
        <dd>{formatMetric(values.hours)}</dd>
      </div>
      <div>
        <dt>Максимум</dt>
        <dd>{formatMetric(values.longest)}</dd>
      </div>
    </dl>
  );
}

function CategoryBody({
  detail,
  category,
}: {
  detail: Loadable<HouseDetailResponse>;
  category: keyof HouseCategories;
}) {
  if (detail.status === 'idle' || detail.status === 'loading') {
    return (
      <div aria-hidden="true" style={{ display: 'grid', gap: 8 }}>
        <div className="skeleton" style={{ height: 24, width: '40%' }} />
        <div className="skeleton" style={{ height: 5, width: '100%' }} />
        <div className="skeleton" style={{ height: 32 }} />
      </div>
    );
  }

  if (detail.status === 'error') {
    return (
      <p className="category-card__empty">
        {detail.error.kind === 'no_data' ? 'Нет исходных данных' : 'Оценка недоступна'}
      </p>
    );
  }

  const categoryDetail = detail.data.categories[category];
  if (categoryDetail === null) {
    return <p className="category-card__empty">Нет записей за период</p>;
  }

  return (
    <>
      <p className="category-card__score text-2xl">
        {formatScore(categoryDetail.score)}
        <small className="sr-only"> / 100</small>
      </p>
      <div className="category-card__track" aria-hidden="true">
        <span
          className="category-card__fill"
          style={{ width: `${categoryDetail.score * 100}%` }}
        />
      </div>
      <Metrics values={categoryDetail.metrics} title={`Метрики: ${categoryLabel(category)}`} />
    </>
  );
}

export function CategoryScores({ detail }: CategoryScoresProps) {
  const pending = detail.status === 'idle' || detail.status === 'loading';

  return (
    <section
      aria-labelledby="category-scores-heading"
      aria-busy={pending}
      className="category-panel"
    >
      <div className="category-panel__head">
        <h3 id="category-scores-heading">Оценки категорий</h3>
        {pending && (
          <p role="status" className="loading-pulse t-small muted" style={{ margin: 0 }}>
            Загружаем оценки…
          </p>
        )}
      </div>

      <div className="category-grid">
        {CATEGORY_ORDER.map((category) => (
          <article key={category} className="category-card">
            <div className="category-card__head">
              <h4 className="category-card__name">
                <span className="category-card__mark" data-category={category} aria-hidden="true" />
                {categoryLabel(category)}
              </h4>
            </div>
            <CategoryBody detail={detail} category={category} />
          </article>
        ))}
      </div>

      <div className="metric-notes">
        {METRIC_NOTES.map((note) => (
          <p key={note}>{note}</p>
        ))}
      </div>

      {detail.status === 'success' && <WeakestCategory detail={detail.data} />}
    </section>
  );
}
