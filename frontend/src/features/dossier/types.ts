export type HouseId = `house_${string}`;

export type UtilityCategory =
  | 'hot_water'
  | 'cold_water'
  | 'electricity'
  | 'heating';

export type EventKind = 'emergency' | 'planned';

export interface Scope {
  kind: 'pilot';
  house_count: 20;
  average_basis: 'pilot_only';
}

export interface TimeWindow {
  /** ISO datetime с offset; для текущего набора +10:00. */
  start: string;
  /** Полуоткрытое окно [start, end). */
  end: string;
}

export interface MetricValues {
  frequency: number;
  hours: number;
  longest: number;
}

export interface CategoryDetail {
  metrics: MetricValues;
  penalties: MetricValues;
  score: number;
}

export interface HouseCategories {
  hot_water: CategoryDetail;
  cold_water: CategoryDetail;
  electricity: CategoryDetail;
  heating: CategoryDetail;
}

export interface HouseSummary {
  house_id: HouseId;
  address: string;
  overall_score: number;
}

export interface HouseListResponse {
  scope: Scope;
  window: TimeWindow;
  houses: HouseSummary[];
}

export interface HouseEvent {
  house_id: HouseId;
  category: UtilityCategory;
  started_at: string;
  /** null означает продолжающееся событие, а не нулевую длительность. */
  ended_at: string | null;
  kind: EventKind;
  is_mass: boolean;
  is_natural_disaster: boolean;
  source_url: string;
}

export interface HouseDetailResponse {
  scope: Scope;
  window: TimeWindow;
  house_id: HouseId;
  address: string;
  overall_score: number;
  categories: HouseCategories;

  /** Вычисляется backend; frontend не ищет минимум самостоятельно. */
  weakest: UtilityCategory;

  /** Пустой массив — корректное отсутствие событий при доступных данных. */
  events: HouseEvent[];
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}
