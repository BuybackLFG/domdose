import { categoryLabel, formatScore } from './format';
import type { HouseDetailResponse } from './types';

interface WeakestCategoryProps {
  detail: HouseDetailResponse;
}

export function WeakestCategory({ detail }: WeakestCategoryProps) {
  const label = categoryLabel(detail.weakest);

  return (
    <section aria-labelledby="weakest-heading" className="rounded-2xl border border-warning/30 bg-warning/10 p-4 sm:p-5">
      <h3 id="weakest-heading" className="text-base font-semibold text-text">
        Худшая категория
      </h3>
      <p className="mt-2 text-xl font-semibold text-warning">
        {label}
        <span className="ml-2 text-sm font-medium text-text-secondary">
          {formatScore(detail.categories[detail.weakest].score)} / 100
        </span>
      </p>
      <p className="mt-2 text-sm leading-6 text-text">
        Она участвует в ограничении общего рейтинга: итог не выше её оценки + 0,25. Это не
        отдельная независимая оценка.
      </p>
    </section>
  );
}
