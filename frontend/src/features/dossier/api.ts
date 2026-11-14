import { requestJson } from '../../lib/api';
import type {
  CategoryDetail,
  EventKind,
  HouseCategories,
  HouseDetailResponse,
  HouseEvent,
  HouseId,
  HouseListResponse,
  HouseSummary,
  MetricValues,
  Scope,
  TimeWindow,
  UtilityCategory,
} from './types';

const HOUSE_ID_PATTERN = /^house_\d{6}$/;
const CATEGORIES: readonly UtilityCategory[] = [
  'hot_water',
  'cold_water',
  'electricity',
  'heating',
];
const EVENT_KINDS: readonly EventKind[] = ['emergency', 'planned'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function isFiniteNonNegative(value: unknown): value is number {
  return isFiniteNumber(value) && value >= 0;
}

function isScore(value: unknown): value is number {
  return isFiniteNumber(value) && value >= 0 && value <= 1;
}

function isTimestamp(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value));
}

function isHouseId(value: unknown): value is HouseId {
  return typeof value === 'string' && HOUSE_ID_PATTERN.test(value);
}

function isCategory(value: unknown): value is UtilityCategory {
  return typeof value === 'string' && CATEGORIES.includes(value as UtilityCategory);
}

function isEventKind(value: unknown): value is EventKind {
  return typeof value === 'string' && EVENT_KINDS.includes(value as EventKind);
}

function validateScope(value: unknown): Scope {
  if (
    !isRecord(value)
    || value.kind !== 'pilot'
    || value.house_count !== 20
    || value.average_basis !== 'pilot_only'
  ) {
    throw new Error('Некорректный scope пилотной выборки');
  }
  return value as unknown as Scope;
}

function validateWindow(value: unknown): TimeWindow {
  if (!isRecord(value) || !isTimestamp(value.start) || !isTimestamp(value.end)) {
    throw new Error('Некорректное окно расчёта');
  }
  if (Date.parse(value.start) >= Date.parse(value.end)) {
    throw new Error('Некорректные границы окна расчёта');
  }
  return { start: value.start, end: value.end };
}

function validateMetricValues(value: unknown, label: string): MetricValues {
  if (
    !isRecord(value)
    || !isFiniteNonNegative(value.frequency)
    || !isFiniteNonNegative(value.hours)
    || !isFiniteNonNegative(value.longest)
  ) {
    throw new Error(`Некорректные метрики: ${label}`);
  }
  return {
    frequency: value.frequency,
    hours: value.hours,
    longest: value.longest,
  };
}

function validateCategory(value: unknown, category: UtilityCategory): CategoryDetail | null {
  if (value === null) return null;
  if (!isRecord(value) || !isScore(value.score)) {
    throw new Error(`Некорректная категория: ${category}`);
  }
  return {
    metrics: validateMetricValues(value.metrics, category),
    penalties: validateMetricValues(value.penalties, category),
    score: value.score,
  };
}

function validateCategories(value: unknown): HouseCategories {
  if (!isRecord(value)) throw new Error('Отсутствуют категории дома');
  return Object.fromEntries(
    CATEGORIES.map((category) => [category, validateCategory(value[category], category)]),
  ) as unknown as HouseCategories;
}

function validateHouseSummary(value: unknown): HouseSummary {
  if (
    !isRecord(value)
    || !isHouseId(value.house_id)
    || !isNonEmptyString(value.address)
    || !(value.overall_score === null || isScore(value.overall_score))
    || !(value.event_count === undefined || (Number.isInteger(value.event_count) && (value.event_count as number) >= 0))
    || !(value.coverage === undefined || value.coverage === 'unknown')
  ) {
    throw new Error('Некорректная карточка дома');
  }
  return {
    house_id: value.house_id,
    address: value.address,
    overall_score: value.overall_score,
    event_count: value.event_count as number | undefined,
    coverage: value.coverage as 'unknown' | undefined,
  };
}

function validateEvent(value: unknown): HouseEvent {
  if (
    !isRecord(value)
    || !isHouseId(value.house_id)
    || !isCategory(value.category)
    || !isTimestamp(value.started_at)
    || !(value.ended_at === null || isTimestamp(value.ended_at))
    || !isEventKind(value.kind)
    || typeof value.is_mass !== 'boolean'
    || typeof value.is_natural_disaster !== 'boolean'
    || !isNonEmptyString(value.source_url)
  ) {
    throw new Error('Некорректное событие дома');
  }
  return {
    house_id: value.house_id,
    category: value.category,
    started_at: value.started_at,
    ended_at: value.ended_at,
    kind: value.kind,
    is_mass: value.is_mass,
    is_natural_disaster: value.is_natural_disaster,
    source_url: value.source_url,
  };
}

export function validateHouseListResponse(value: unknown): HouseListResponse {
  if (!isRecord(value) || !Array.isArray(value.houses)) {
    throw new Error('Некорректный ответ списка домов');
  }
  if (value.houses.length !== 20) {
    throw new Error('Пилотная выборка должна содержать ровно 20 домов');
  }

  const houses = value.houses.map(validateHouseSummary);
  if (new Set(houses.map((house) => house.house_id)).size !== houses.length) {
    throw new Error('Пилотная выборка содержит повторяющиеся дома');
  }

  return {
    scope: validateScope(value.scope),
    window: validateWindow(value.window),
    houses,
  };
}

export function validateHouseDetailResponse(value: unknown): HouseDetailResponse {
  if (!isRecord(value)) throw new Error('Некорректный ответ досье дома');
  const summary = validateHouseSummary(value);
  if (!Array.isArray(value.events)) throw new Error('Отсутствует список событий');
  if (!(value.weakest === null || isCategory(value.weakest))) throw new Error('Некорректная худшая категория');

  return {
    scope: validateScope(value.scope),
    window: validateWindow(value.window),
    house_id: summary.house_id,
    address: summary.address,
    overall_score: summary.overall_score,
    event_count: summary.event_count,
    coverage: summary.coverage,
    categories: validateCategories(value.categories),
    weakest: value.weakest,
    events: value.events.map(validateEvent),
  };
}

export function fetchHouseList(signal?: AbortSignal): Promise<HouseListResponse> {
  return requestJson('/api/houses', validateHouseListResponse, signal);
}

export function fetchHouseDetail(houseId: HouseId, signal?: AbortSignal): Promise<HouseDetailResponse> {
  return requestJson(`/api/houses/${encodeURIComponent(houseId)}`, validateHouseDetailResponse, signal);
}
