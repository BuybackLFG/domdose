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
    <form className="search" onSubmit={handleSubmit} role="search">
      <label htmlFor="house-search-input" className="sr-only">
        Найти адрес
      </label>
      <div className="search__row">
        <div className="search__field">
          <IconSearch size={18} aria-hidden className="search__icon" />
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
            placeholder="Улица и номер дома"
            autoComplete="off"
            className="search__input"
          />
        </div>
        <button type="submit" className="btn btn--primary search__submit">
          Найти дом
        </button>
      </div>

      {isOpen && (
        <ul
          id="house-search-listbox"
          role="listbox"
          aria-label="Результаты поиска"
          className="search__list"
        >
          {search.matches.map((house, index) => (
            <li key={house.house_id}>
              <button
                type="button"
                role="option"
                id={optionId(index)}
                aria-selected={search.kind === 'open' && index === search.activeIndex}
                onClick={() => onSelect(house.house_id)}
                className="search__option"
              >
                {house.address}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div aria-live="polite">
        {search.kind === 'not_covered' && (
          <p className="search__message search__message--warn">
            Этот адрес не входит в список домов. Это не означает отсутствие отключений или
            плохой рейтинг.
          </p>
        )}
        {search.kind === 'unsupported_link' && (
          <p className="search__message search__message--warn">
            Ссылки на объявления пока не открываются и не проверяются онлайн. Введите адрес
            текстом.
          </p>
        )}
      </div>
    </form>
  );
}
