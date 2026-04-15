import { describe, expect, it } from 'vitest';

import {
  resolveActiveSearchIndex,
  updateActiveSearchHighlight,
} from './searchHighlights';

describe('searchHighlights', () => {
  it('preserves the base search class while switching the active match', () => {
    const container = document.createElement('div');
    container.innerHTML = `
      <mark class="search-highlight">first</mark>
      <mark class="search-highlight">second</mark>
      <mark class="search-highlight">third</mark>
    `;

    updateActiveSearchHighlight(container.querySelectorAll('mark'), 1);

    const marks = Array.from(container.querySelectorAll('mark.search-highlight'));

    expect(marks).toHaveLength(3);
    expect(marks[0]).not.toHaveClass('search-highlight-active');
    expect(marks[1]).toHaveClass('search-highlight-active');
    expect(marks[2]).not.toHaveClass('search-highlight-active');
  });

  it('restores the searchable class even if another class was applied earlier', () => {
    const container = document.createElement('div');
    container.innerHTML = `
      <mark class="bg-yellow-200">first</mark>
      <mark class="bg-amber-400">second</mark>
    `;

    updateActiveSearchHighlight(container.querySelectorAll('mark'), 0);

    const marks = Array.from(container.querySelectorAll('mark.search-highlight'));

    expect(marks).toHaveLength(2);
    expect(marks[0]).toHaveClass('search-highlight-active');
    expect(marks[1]).not.toHaveClass('search-highlight-active');
  });

  it('resets the active index when the current result is out of bounds', () => {
    expect(resolveActiveSearchIndex(-1, 4)).toBe(0);
    expect(resolveActiveSearchIndex(7, 2)).toBe(0);
    expect(resolveActiveSearchIndex(1, 4)).toBe(1);
    expect(resolveActiveSearchIndex(0, 0)).toBe(-1);
  });
});
