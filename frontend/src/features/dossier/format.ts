import type { UtilityCategory } from './types';

const DATE_TIME_FORMAT = new Intl.DateTimeFormat('ru-RU', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Asia/Vladivostok',
});

const CATEGORY_LABELS: Record<UtilityCategory, string> = {
  hot_water: 'Горячая вода',
  cold_water: 'Холодная вода',
  electricity: 'Электричество',
  heating: 'Отопление',
};

export function formatScore(score: number): string {
  return `${(score * 100).toLocaleString('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  })}`;
}

export function formatDateTime(value: string): string {
  return DATE_TIME_FORMAT.format(new Date(value));
}

export function categoryLabel(category: UtilityCategory): string {
  return CATEGORY_LABELS[category];
}
