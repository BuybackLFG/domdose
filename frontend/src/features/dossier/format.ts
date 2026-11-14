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

export function formatScore(score: number): string {
  return `${(score * 100).toLocaleString('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  })}`;
}

export function formatDateTime(value: string): string {
  return DATE_TIME_FORMAT.format(new Date(value));
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
