import { api } from './http';
import type { ListMeta } from './documents';

export interface Job {
  id: string; document_id: string; version_id: string | null; job_type: string; status: string;
  filename: string | null; document_title: string | null;
  current_stage: string; processed_pages: number; total_pages: number; attempt_count: number;
  max_attempts: number; heartbeat_at: string | null;
  retry_of_job_id: string | null; error: { code: string | null; message: string | null } | null;
  created_at: string; started_at: string | null; finished_at: string | null;
}

export const JOB_STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  parsing: '解析中',
  embedding: '向量化中',
  pending_confirmation: '待确认切分',
  completed: '已完成',
  partial_success: '部分成功',
  failed: '失败',
  cancelled: '已取消',
};

export const JOB_STAGE_LABELS: Record<string, string> = {
  validation: '校验文件',
  extraction: '提取文本',
  mineru: 'MinerU 结构化解析',
  ocr: 'OCR 识别扫描页',
  cleaning: '清洗文本',
  masking: '脱敏处理',
  chunking: '切分文本块',
  review: '等待人工确认切分',
  embedding: '生成向量',
  indexing: '建立索引',
  publishing: '发布检索',
  cleanup: '清理临时数据',
};

export const JOB_TYPE_LABELS: Record<string, string> = {
  upload: '上传处理',
  retry: '失败重试',
  reprocess: '重新处理',
  rollback: '版本回滚',
  delete: '删除清理',
  masking: '脱敏修正',
  rebuild: '索引重建',
};

/** 用上传时的原始文件名区分任务，取不到时再退化为文档标题 / 文档 ID。 */
export function jobDisplayName(job: Pick<Job, 'filename' | 'document_title' | 'document_id'>): string {
  return job.filename || job.document_title || `文档 ${job.document_id.slice(0, 8)}`;
}

export async function listJobs(
  params: {
    page?: number;
    page_size?: number;
    status?: string;
    document_id?: string;
    ids?: string[];
  } = {},
) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value == null) return;
    query.set(key, Array.isArray(value) ? value.join(',') : String(value));
  });
  return api<{ items: Job[]; meta: ListMeta }>(`/jobs?${query.toString()}`);
}

export async function getJob(id: string) { return api<Job>(`/jobs/${id}`); }

export async function cancelJob(id: string) { return api<Job>(`/jobs/${id}/cancel`, { method: 'POST' }); }
export async function retryJob(id: string) { return api<Job>(`/jobs/${id}/retry`, { method: 'POST' }); }
