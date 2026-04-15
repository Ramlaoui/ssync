export function resolveActiveSearchIndex(
  currentIndex: number,
  matchCount: number
): number {
  if (matchCount === 0) return -1;

  return currentIndex >= 0 && currentIndex < matchCount ? currentIndex : 0;
}

export function updateActiveSearchHighlight(
  marks: Iterable<Element>,
  activeIndex: number
): void {
  Array.from(marks).forEach((mark, index) => {
    if (!(mark instanceof HTMLElement)) return;

    mark.classList.add('search-highlight');
    mark.classList.toggle('search-highlight-active', index === activeIndex);
  });
}
