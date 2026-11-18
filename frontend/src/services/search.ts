import { api } from './http';
import type { Category, Tag } from './documents';

export interface TableCell {
  text: string;
  rowspan: number;
  colspan: number;
}
export interface TableInfo {
  id: string;
  caption: string | null;
  header: string | null;
  total_rows: number;
  row_count?: number;
  column_count?: number;
  row_range?: [number, number];
  rows: TableCell[][];
}
export interface SearchResult {
  chunk_id: string; matched_chunk_id?: string | null; text: string; document_id: string; document_name: string; version_number: number;
  page_start: number; page_end: number; category: Category | null; tags: Tag[];
  lifecycle_status: string; document_role: string; standard_no?: string | null;
  related_documents?: { document_id: string; title: string; relation_type: string; volume_no?: string | null }[];
  amendment_notice?: string | null;
  scores: { semantic?: number | null; keyword?: number | null; rrf: number };
  recall_sources: string[]; highlights: { start_offset: number; end_offset: number }[];
  kind: 'chunk' | 'table';
  table: TableInfo | null;
}
export interface SearchData {
  items: SearchResult[]; total: number; took_ms: number; mode: string; ranking: string;
  degraded: boolean; degraded_sources: string[]; suggestions: string[];
}
export interface SearchParams {
  query: string; mode: 'semantic' | 'keyword' | 'hybrid'; top_k: number;
  filters?: {
    document_ids?: string[];
    category_ids?: string[];
    tag_ids?: string[];
    // "text" 正文 / "table" 表格；不传则不过滤。
    block_types?: string[];
    scenario_ids?: string[];
    include_replaced?: boolean;
  };
  include_raw?: boolean;
}

export async function search(params: SearchParams) {
  return api<SearchData>('/search', { method: 'POST', body: JSON.stringify(params) });
}
