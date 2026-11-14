import type { TimeWindow, UtilityCategory } from './types';

const DATE_TIME_FORMAT = new Intl.DateTimeFormat('ru-RU', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Asia/Vladivostok',
});

const DATE_FORMAT = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'Asia/Vladivostok',
});

const DAY_FORMAT = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  timeZone: 'Asia/Vladivostok',
});

const PLURAL_RULES = new Intl.PluralRules('ru-RU');

const ADDRESS_FORMS: Partial<Record<Intl.LDMLPluralRule, string>> = {
  one: 'адрес',
  few: 'адреса',
  many: 'адресов',
};

const CATEGORY_LABELS: Record<UtilityCategory, string> = {
  hot_water: 'Горячая вода',
  cold_water: 'Холодная вода',
  electricity: 'Электричество',
  heating: 'Отопление',
};

export type ScoreBand = 'good' | 'mid' | 'bad' | 'none';

export function formatScore(score: number): string {
  return `${(score * 100).toLocaleString('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  })}`;
}

/** Полоса индекса для маркеров, столбиков и подписи сводки. */
export function scoreBand(score: number | null): ScoreBand {
  if (score === null) return 'none';
  if (score >= 0.9) return 'good';
  if (score >= 0.75) return 'mid';
  return 'bad';
}

export function formatDateTime(value: string): string {
  return DATE_TIME_FORMAT.format(new Date(value));
}

/** Дата без года и времени: «22 окт.». */
export function formatDay(value: string): string {
  return DAY_FORMAT.format(new Date(value));
}

/** Период окна датами без времени и пояса: «14 окт. 2026 г. – 13 нояб. 2026 г.». */
export function formatPeriod(window: TimeWindow): string {
  return `${DATE_FORMAT.format(new Date(window.start))} – ${DATE_FORMAT.format(new Date(window.end))}`;
}

/** Число адресов с русским склонением: 1 адрес, 2 адреса, 5 адресов. */
export function formatAddressCount(count: number): string {
  return `${count} ${ADDRESS_FORMS[PLURAL_RULES.select(count)] ?? 'адреса'}`;
}

export function categoryLabel(category: UtilityCategory): string {
  return CATEGORY_LABELS[category];
}
