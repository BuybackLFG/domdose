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
    <section aria-labelledby="weakest-heading" className="rounded-2xl border border-warning/30 bg-warning/10 p-4 sm:p-5">
      <h3 id="weakest-heading" className="text-base font-semibold text-text">
        Худшая категория
      </h3>
      <p className="mt-2 text-xl font-semibold text-warning">
        {categoryLabel(detail.weakest)}
        <span className="ml-2 text-sm font-medium text-text-secondary">
          {formatScore(weakest.score)} / 100
        </span>
      </p>
    </section>
  );
}
