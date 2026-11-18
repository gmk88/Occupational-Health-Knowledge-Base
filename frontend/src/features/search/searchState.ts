export interface SearchState {
  query: string;
  mode: 'semantic' | 'keyword' | 'hybrid';
  categoryId: string;
  tagId: string;
  blockType: string;
}

const KEY = 'oh.search.session';

export function saveSearchState(state: SearchState) {
  try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch { /* ignore */ }
}

export function loadSearchState(): SearchState | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as SearchState) : null;
  } catch { return null; }
}
