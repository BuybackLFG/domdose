import { categoryLabel, formatScore } from './format';
import type { HouseDetailResponse } from './types';

interface WeakestCategoryProps {
  detail: HouseDetailResponse;
}

/** Категория из поля weakest ответа; при всех четырёх оценках 1 блок не показывается. */
export function WeakestCategory({ detail }: WeakestCategoryProps) {
  const weakest = detail.weakest === null ? null : detail.categories[detail.weakest];
  if (detail.weakest === null || weakest === null || weakest.score === 1) return null;

  return (
    <section aria-labelledby="weakest-heading" className="weakest">
      <div>
        <h4 id="weakest-heading" className="weakest__label">
          Худшая категория
        </h4>
        <p className="weakest__value">
          {categoryLabel(detail.weakest)}
          <b className="weakest__score">{formatScore(weakest.score)}</b>
          <span className="sr-only">/ 100</span>
        </p>
      </div>
    </section>
  );
}
