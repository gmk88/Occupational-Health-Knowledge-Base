import { ApiError, api, type Envelope } from './http';

export interface Category { id: string; code: string; name: string; active: boolean }
export interface Tag { id: string; name: string }
export interface DocumentVersion { id: string; version_number: number; status: string; content_sha256: string }
export interface Document {
  id: string; title: string; original_filename: string | null; status: string;
  category: Category | null; tags: Tag[]; source: string | null; notes: string | null;
  uploader_id: string; current_version: DocumentVersion | null; created_at: string; updated_at: string;
}
export interface ListMeta { page: number; page_size: number; total: number; total_pages: number }
export interface QualityReport {
  document_id: string; version_id: string; job_id: string; page_count: number; effective_char_count: number;
  chunk_count: number; ocr_page_ratio: number; average_ocr_confidence: number | null; noise_char_count: number;
  low_quality_pages: number[]; failed_pages: unknown[]; processing_duration_ms: number; created_at: string;
}
export interface PageText {
  document_id: string; version_number: number; page_number: number; source_type: string; view: 'masked' | 'raw';
  text: string; spans: unknown[]; quality_warnings: string[];
}
export interface Limits { max_file_size_bytes: number; max_pages_per_file: number; max_files_per_web_batch: number; upload_limit_per_minute: number }

export async function listDocuments(params: { page?: number; page_size?: number; status?: string; category_id?: string } = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => { if (value != null) query.set(key, String(value)); });
  return api<{ items: Document[]; meta: ListMeta }>(`/documents?${query.toString()}`);
}

export async function getDocument(id: string) { return api<Document>(`/documents/${id}`); }
export async function getQualityReport(id: string) { return api<QualityReport>(`/documents/${id}/quality-report`); }
export async function getPage(id: string, pageNumber: number, view: 'masked' | 'raw' = 'masked') {
  return api<PageText>(`/documents/${id}/pages/${pageNumber}?view=${view}`);
}
export async function getLimits() { return api<Limits>('/system/limits'); }

// 上传页会被频繁重渲染；模块级缓存保证一次会话只取一次限额。
let limitsPromise: Promise<Envelope<Limits>> | null = null;
export function getLimitsCached() {
  if (!limitsPromise) {
    limitsPromise = getLimits().catch((error) => {
      limitsPromise = null;
      throw error;
    });
  }
  return limitsPromise;
}

export async function listCategories() { return api<Category[]>('/categories'); }

export async function autoClassifyDocuments() {
  return api<{ documents: number; category_updated: number; tags_linked?: number }>(
    '/documents/auto-classify',
    { method: 'POST' },
  );
}

export async function listTags(params: { page?: number; page_size?: number; q?: string } = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => { if (value != null) query.set(key, String(value)); });
  return api<{ items: Tag[]; meta: ListMeta }>(`/tags?${query.toString()}`);
}

export async function deleteDocument(id: string) { return api<{ document_id: string; status: string }>(`/documents/${id}`, { method: 'DELETE' }); }
export async function reprocessDocument(id: string) { return api<{ id: string; status: string }>(`/documents/${id}/reprocess`, { method: 'POST' }); }
export async function listVersions(id: string) { return api<DocumentVersion[]>(`/documents/${id}/versions`); }
export async function rollbackVersion(id: string, versionNumber: number) {
  return api<{ version_number: number; status: string }>(`/documents/${id}/versions/${versionNumber}/rollback`, { method: 'POST' });
}
export async function updateDocumentMetadata(
  id: string,
  patch: { tags?: string[]; title?: string; source?: string | null; notes?: string | null },
) {
  return api<Document>(`/documents/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
}

export async function exportDocuments(): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch('/api/v1/documents/export', {
      method: 'GET',
      credentials: 'same-origin',
    });
  } catch (caught) {
    if (caught instanceof TypeError) {
      throw new ApiError(0, 'NETWORK_ERROR', '无法连接服务，请确认后端已启动后重试', null, '');
    }
    throw caught;
  }
  if (!response.ok) {
    let body: Envelope<unknown> | null = null;
    try {
      body = (await response.json()) as Envelope<unknown>;
    } catch {
      body = null;
    }
    throw new ApiError(
      response.status,
      body?.code ?? 'HTTP_ERROR',
      body?.message ?? '导出失败，请稍后重试',
      body?.data ?? null,
      body?.request_id ?? '',
    );
  }
  return response.blob();
}

export async function uploadDocument(file: File, options: {
  title?: string; category_id?: string; tags?: string[];
  chunk_mode?: string; chunk_target_tokens?: number; chunk_max_tokens?: number; chunk_overlap_tokens?: number;
} = {}) {
  const form = new FormData();
  form.set('file', file);
  if (options.title) form.set('title', options.title);
  if (options.category_id) form.set('category_id', options.category_id);
  if (options.tags?.length) form.set('tags', options.tags.join(','));
  if (options.chunk_mode) form.set('chunk_mode', options.chunk_mode);
  if (options.chunk_target_tokens != null) form.set('chunk_target_tokens', String(options.chunk_target_tokens));
  if (options.chunk_max_tokens != null) form.set('chunk_max_tokens', String(options.chunk_max_tokens));
  if (options.chunk_overlap_tokens != null) form.set('chunk_overlap_tokens', String(options.chunk_overlap_tokens));
  let response: Response;
  try {
    response = await fetch('/api/v1/documents', { method: 'POST', body: form, credentials: 'same-origin' });
  } catch (caught) {
    if (caught instanceof TypeError) {
      throw new ApiError(0, 'NETWORK_ERROR', '无法连接服务，请确认后端已启动后重试', null, '');
    }
    throw caught;
  }
  let body: Envelope<{ document_id: string; version_id: string; job_id: string | null; duplicate: boolean; status: string | null }>;
  try {
    body = (await response.json()) as Envelope<{ document_id: string; version_id: string; job_id: string | null; duplicate: boolean; status: string | null }>;
  } catch {
    throw new ApiError(response.status, 'BAD_RESPONSE', '服务返回异常响应，请稍后重试', null, '');
  }
  if (!response.ok) {
    const retry = Number(response.headers.get('retry-after'));
    throw new ApiError(
      response.status,
      body?.code ?? 'HTTP_ERROR',
      body?.message ?? '上传失败，请稍后重试',
      body?.data ?? null,
      body?.request_id ?? '',
      Number.isFinite(retry) && retry > 0 ? retry : undefined,
    );
  }
  return body.data;
}
