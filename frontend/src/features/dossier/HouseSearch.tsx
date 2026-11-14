import { IconSearch } from '@tabler/icons-react';
import type { FormEvent, KeyboardEvent } from 'react';
import type { SearchState } from './useHouseDossier';
import type { HouseSummary } from './types';

interface HouseSearchProps {
  query: string;
  search: SearchState;
  onQueryChange: (value: string) => void;
  onMoveActive: (direction: 1 | -1) => void;
  onSubmit: () => void;
  onSelect: (houseId: HouseSummary['house_id']) => void;
}

function optionId(index: number): string {
  return `house-search-option-${index}`;
}

export function HouseSearch({
  query,
  search,
  onQueryChange,
  onMoveActive,
  onSubmit,
  onSelect,
}: HouseSearchProps) {
  const isOpen = search.kind === 'open' && search.matches.length > 0;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      onMoveActive(1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      onMoveActive(-1);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      onSubmit();
    }
  };

  return (
    <section aria-labelledby="house-search-heading" className="rounded-2xl bg-surface p-4 shadow-sm ring-1 ring-border sm:p-5">
      <div className="flex flex-col gap-3">
        <h2 id="house-search-heading" className="text-base font-semibold text-text">
          Найти дом
        </h2>

        <form onSubmit={handleSubmit} className="relative">
          <label htmlFor="house-search-input" className="sr-only">
            Найти адрес
          </label>
          <IconSearch size={17} aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary" />
          <input
            id="house-search-input"
            role="combobox"
            aria-expanded={isOpen}
            aria-controls="house-search-listbox"
            aria-activedescendant={isOpen ? optionId(search.kind === 'open' ? search.activeIndex : 0) : undefined}
            aria-autocomplete="list"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Например: Тобольская 29"
            autoComplete="off"
            className="h-11 w-full rounded-xl border border-border bg-surface-subtle pl-10 pr-24 text-sm text-text outline-none transition focus:border-accent focus:bg-surface"
          />
          <button
            type="submit"
            className="absolute right-1 top-1 h-9 rounded-lg bg-accent px-3 text-sm font-medium text-white transition hover:bg-accent-hover"
          >
            Найти
          </button>

          {isOpen && (
            <ul
              id="house-search-listbox"
              role="listbox"
              aria-label="Результаты поиска"
              className="absolute left-0 right-0 top-full z-30 mt-2 max-h-72 overflow-y-auto rounded-xl bg-surface p-2 shadow-lg ring-1 ring-border"
            >
              {search.matches.map((house, index) => (
                <li key={house.house_id}>
                  <button
                    type="button"
                    role="option"
                    id={optionId(index)}
                    aria-selected={search.kind === 'open' && index === search.activeIndex}
                    onClick={() => onSelect(house.house_id)}
                    className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${
                      search.kind === 'open' && index === search.activeIndex
                        ? 'bg-accent-soft text-accent'
                        : 'text-text hover:bg-surface-subtle'
                    }`}
                  >
                    {house.address}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </form>

        <div aria-live="polite">
          {search.kind === 'not_covered' && (
            <p className="rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-text">
              Этот адрес не входит в список домов. Это не означает отсутствие отключений или
              плохой рейтинг.
            </p>
          )}
          {search.kind === 'unsupported_link' && (
            <p className="rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-text">
              Ссылки на объявления пока не открываются и не проверяются онлайн. Введите адрес
              текстом.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
