import type { HouseSummary } from './types';

export function normalizeHouseQuery(value: string): string {
  return value
    .toLocaleLowerCase('ru-RU')
    .replace(/ё/g, 'е')
    .trim()
    .replace(/\s+/g, ' ');
}

function compactAddress(value: string): string {
  return normalizeHouseQuery(value)
    .replace(/^владивосток,\s*/, '')
    .replace(/(?:^|[\s,])(?:улица|ул|дом|д)(?=[\s,]|$)/g, ' ')
    .replace(/,/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function isListingUrl(value: string): boolean {
  return /^(?:https?:\/\/|www\.)/i.test(value.trim());
}

export function searchHouses(houses: HouseSummary[], query: string): HouseSummary[] {
  const normalized = normalizeHouseQuery(query);
  if (!normalized || isListingUrl(normalized)) return [];

  return houses.filter((house) => {
    const address = normalizeHouseQuery(house.address);
    const compact = compactAddress(house.address);
    return address.includes(normalized) || compact.includes(normalized);
  });
}
