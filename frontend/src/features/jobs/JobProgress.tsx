import { useEffect, useRef, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { JOB_STAGE_LABELS, JOB_STATUS_LABELS, type Job } from '../../services/jobs';
import { subscribeJob } from '../../services/jobPolling';

// 待确认也是阶段一终态：停止轮询，由确认页接管后续向量化。
const TERMINAL_STATUSES = [
  'pending_confirmation',
  'completed',
  'partial_success',
  'failed',
  'cancelled',
];

function parseUtc(value: string | null | undefined): number | null {
  if (!value) return null;
  const normalized = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`;
  const timestamp = Date.parse(normalized);
  return Number.isNaN(timestamp) ? null : timestamp;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} 分 ${seconds % 60} 秒`;
}

export function JobProgress({
  jobId,
  filename,
  onSettled,
}: {
  jobId: string;
  filename?: string;
  onSettled?: () => void;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const onSettledRef = useRef(onSettled);

  useEffect(() => {
    onSettledRef.current = onSettled;
  }, [onSettled]);

  useEffect(() => {
    const clock = window.setInterval(() => setNow(Date.now()), 2000);
    return () => window.clearInterval(clock);
  }, []);

  useEffect(() => {
    let active = true;
    let unsubscribe = () => {};
    unsubscribe = subscribeJob(jobId, (next) => {
      if (!active) return;
      setJob(next);
      if (TERMINAL_STATUSES.includes(next.status)) {
        active = false;
        onSettledRef.current?.();
        unsubscribe();
      }
    });
    return () => {
      active = false;
      unsubscribe();
    };
  }, [jobId]);

  const status = job?.status ?? 'queued';
  const stage = job?.current_stage ?? '';
  const failed = ['failed', 'cancelled'].includes(status);
  const terminal = TERMINAL_STATUSES.includes(status);
  const done = job?.processed_pages ?? 0;
  const total = job?.total_pages ?? 0;
  const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const indeterminate = !terminal && (
    percent === 0 || ['ocr', 'embedding', 'indexing', 'publishing'].includes(stage)
  );
  const started = parseUtc(job?.started_at);
  const heartbeat = parseUtc(job?.heartbeat_at);
  const elapsed = started ? Math.max(0, Math.floor((now - started) / 1000)) : null;
  const heartbeatAge = heartbeat ? Math.max(0, Math.floor((now - heartbeat) / 1000)) : null;

  const detailParts: string[] = [];
  if (JOB_STAGE_LABELS[stage]) detailParts.push(`阶段：${JOB_STAGE_LABELS[stage]}`);
  if (total > 0) detailParts.push(`${done}/${total} 页`);
  if (stage === 'mineru' && !terminal) {
    detailParts.push('整份文档结构化解析中，解析完才会逐页写入');
  }
  if (!terminal && job?.attempt_count) {
    detailParts.push(`第 ${job.attempt_count + 1}/${job.max_attempts ?? 3} 次尝试`);
  }
  if (!terminal && elapsed !== null) detailParts.push(`已耗时 ${formatDuration(elapsed)}`);
  if (!terminal && heartbeatAge !== null) detailParts.push(`心跳 ${heartbeatAge} 秒前`);
  if (status === 'pending_confirmation') {
    detailParts.push('切分已完成，需你预览确认后才会向量化入库');
  }
  if (job?.error?.message) detailParts.push(job.error.message);

  return (
    <div className={`upload-job${failed ? ' is-failed' : ''}`} aria-live="polite">
      <div className="upload-job-head">
        <span className="upload-job-name">{filename ?? job?.filename ?? job?.document_title ?? '文档'}</span>
        <span className="upload-job-status" data-status={status}>
          {JOB_STATUS_LABELS[status] ?? status}
        </span>
      </div>
      <div
        className={`progress upload-job-bar${indeterminate ? ' is-indeterminate' : ''}`}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indeterminate ? undefined : percent}
        aria-label={`文档处理进度：${filename ?? job?.filename ?? job?.document_title ?? '文档'}`}
      >
        <div style={indeterminate ? undefined : { width: `${percent}%` }} />
      </div>
      <p className="hint upload-job-detail">
        {detailParts.length > 0 ? detailParts.join(' · ') : '正在提交向量化任务…'}
      </p>
      {status === 'pending_confirmation' && (
        <NavLink className="button button-secondary upload-job-link" to="/review">
          去预览并确认切分
        </NavLink>
      )}
    </div>
  );
}
