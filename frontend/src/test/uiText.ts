import { expect } from 'vitest';

/** Пробелы, U+00A0 и U+202F сводятся к одному пробелу; края обрезаются. */
export function normalizeText(value: string): string {
  return value.replace(/[\s  ]+/g, ' ').trim();
}

interface ForbiddenFragment {
  fragment: string;
  ignoreCase: boolean;
}

/** Подстроки, которых нет ни в тексте, ни в доступных именах страницы. */
export const FORBIDDEN_UI_FRAGMENTS: readonly ForbiddenFragment[] = [
  { fragment: 'пилот', ignoreCase: true },
  { fragment: 'MVP', ignoreCase: false },
  { fragment: 'Ровно 20', ignoreCase: false },
  { fragment: 'Локальный поиск работает только', ignoreCase: false },
  { fragment: 'Окно расчёта', ignoreCase: false },
  { fragment: 'UTC+10', ignoreCase: false },
];

const NAME_ATTRIBUTES = ['aria-label', 'title', 'alt', 'placeholder'] as const;

/** Текстовые узлы и атрибуты доступных имён поддерева как отдельные строки. */
export function collectRenderedStrings(root: Element = document.body): string[] {
  const strings: string[] = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const textParts: string[] = [];
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    textParts.push(node.textContent ?? '');
  }
  strings.push(normalizeText(textParts.join(' ')));

  const selector = NAME_ATTRIBUTES.map((name) => `[${name}]`).join(', ');
  for (const element of [root, ...root.querySelectorAll(selector)]) {
    for (const name of NAME_ATTRIBUTES) {
      const value = element.getAttribute(name);
      if (value !== null) strings.push(`@${name}: ${normalizeText(value)}`);
    }
  }
  return strings;
}

/** Найденные запрещённые подстроки с контекстом вхождения. */
export function findForbiddenFragments(root: Element = document.body): string[] {
  const hits: string[] = [];
  for (const value of collectRenderedStrings(root)) {
    for (const { fragment, ignoreCase } of FORBIDDEN_UI_FRAGMENTS) {
      const haystack = ignoreCase ? value.toLowerCase() : value;
      const needle = ignoreCase ? fragment.toLowerCase() : fragment;
      const index = haystack.indexOf(needle);
      if (index >= 0) {
        const context = value.slice(Math.max(0, index - 40), index + needle.length + 40);
        hits.push(`${fragment} ← «${context}»`);
      }
    }
  }
  return hits;
}

/** Проверка отсутствия запрещённых подстрок с перечнем найденного в сообщении. */
export function expectNoForbiddenFragments(root: Element = document.body): void {
  const hits = findForbiddenFragments(root);
  expect(hits, `запрещённые подстроки:\n${hits.join('\n')}`).toEqual([]);
}

/** Самые глубокие элементы, нормализованный текст которых содержит target. */
export function deepestElementsContaining(root: Element, target: string): Element[] {
  const wanted = normalizeText(target);
  const candidates = [root, ...root.querySelectorAll('*')].filter((element) => (
    normalizeText(element.textContent ?? '').includes(wanted)
  ));
  return candidates.filter((element) => (
    !Array.from(element.children).some((child) => (
      normalizeText(child.textContent ?? '').includes(wanted)
    ))
  ));
}

/** Скрыт ли элемент от зрения: sr-only, hidden, aria-hidden или закрытый details. */
export function hiddenFromSightReason(element: Element): string | null {
  for (let current: Element | null = element; current !== null; current = current.parentElement) {
    if (current.classList.contains('sr-only')) return 'sr-only';
    if (current.hasAttribute('hidden')) return 'hidden';
    if (current.getAttribute('aria-hidden') === 'true') return 'aria-hidden';
    if (current.tagName === 'DETAILS' && !current.hasAttribute('open') && current !== element) {
      const summary = current.querySelector(':scope > summary');
      if (!summary || !summary.contains(element)) return 'closed details';
    }
  }
  return null;
}
