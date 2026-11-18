import { api } from './http';
import { listJobs, type Job } from './jobs';

export interface ChunkItem {
  id: string;
  chunk_role?: string;
  ordinal: number;
  page_start: number;
  page_end: number;
  block_type: string;
  table_header: string | null;
  table_id: string | null;
  section_title: string | null;
  table_html: string | null;
  text: string;
  raw_text: string;
  token_count: number;
  is_edited: boolean;
  index_visible: boolean;
  merged: boolean;
}

export interface TableInfo {
  table_id: string;
  section_title: string | null;
  header: string | null;
  row_count: number;
  page_start: number;
  page_end: number;
  merged: boolean;
}

export interface ChunkReview {
  job: {
    id: string;
    status: string;
    filename: string | null;
    document_title: string | null;
    document_id: string;
    total_pages: number;
    created_at: string;
  };
  editable: boolean;
  items: ChunkItem[];
  tables: TableInfo[];
}

export function getChunks(jobId: string) {
  return api<ChunkReview>(`/jobs/${jobId}/chunks`);
}

export function updateChunk(jobId: string, chunkId: string, text: string) {
  return api<ChunkItem>(`/chunks/${chunkId}`, {
    method: 'PUT',
    body: JSON.stringify({ job_id: jobId, text }),
  });
}

export function deleteChunk(jobId: string, chunkId: string) {
  return api<{ id: string; deleted: boolean }>(
    `/chunks/${chunkId}?job_id=${encodeURIComponent(jobId)}`,
    { method: 'DELETE' },
  );
}

export function mergeChunks(jobId: string, chunkIds: string[]) {
  return api<{ items: ChunkItem[] }>(`/jobs/${jobId}/chunks/merge`, {
    method: 'POST',
    body: JSON.stringify({ chunk_ids: chunkIds }),
  });
}

export function unmergeChunk(jobId: string, chunkId: string) {
  return api<{ items: ChunkItem[] }>(`/chunks/${chunkId}/unmerge`, {
    method: 'POST',
    body: JSON.stringify({ job_id: jobId }),
  });
}

export function confirmChunks(jobId: string) {
  return api<{ job_id: string; status: string; chunk_count: number }>(
    `/jobs/${jobId}/confirm`,
    { method: 'POST' },
  );
}

export const PENDING_STATUS = 'pending_confirmation';

export async function listPendingJobs(): Promise<Job[]> {
  const response = await listJobs({ status: PENDING_STATUS, page_size: 50 });
  return response.data.items;
}
