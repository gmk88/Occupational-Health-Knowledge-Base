import { ApiError } from './http';
import { getJob, listJobs, type Job } from './jobs';

// 多个上传任务共用同一个轮询器：一个定时器、一次请求，避免每个文件各起一个
// 2.5 秒轮询。页面隐藏时暂停，失败时指数退避。
type Listener = (job: Job) => void;

const TERMINAL_STATUSES = new Set([
  'pending_confirmation',
  'completed',
  'partial_success',
  'failed',
  'cancelled',
]);
const BASE_INTERVAL_MS = 4000;
const MAX_BACKOFF_MS = 30_000;

const listeners = new Map<string, Set<Listener>>();
const missingCounts = new Map<string, number>();
let timer = 0;
let inflight = false;
let failures = 0;
let visibilityBound = false;

function schedule(delay?: number): void {
  if (listeners.size === 0) return;
  window.clearTimeout(timer);
  const backoff = Math.min(BASE_INTERVAL_MS * 2 ** failures, MAX_BACKOFF_MS);
  timer = window.setTimeout(() => void poll(), delay ?? backoff + Math.random() * 500);
}

async function poll(): Promise<void> {
  if (inflight || listeners.size === 0) return;
  if (document.visibilityState === 'hidden') {
    schedule();
    return;
  }
  inflight = true;
  try {
    const ids = Array.from(listeners.keys());
    const response = await listJobs({ ids, page: 1, page_size: 100 });
    const byId = new Map(response.data.items.map((job) => [job.id, job]));
    const missing: string[] = [];
    for (const [id, subscribers] of Array.from(listeners.entries())) {
      const job = byId.get(id);
      if (!job) {
        missing.push(id);
        continue;
      }
      missingCounts.delete(id);
      subscribers.forEach((listener) => listener(job));
      if (TERMINAL_STATUSES.has(job.status)) listeners.delete(id);
    }
    await resolveMissing(missing);
    failures = 0;
  } catch {
    failures = Math.min(failures + 1, 3);
  } finally {
    inflight = false;
    schedule();
  }
}

/** 连续两轮缺席的任务单独查一次；确认 404 后移除订阅。 */
async function resolveMissing(ids: string[]): Promise<void> {
  await Promise.all(
    ids.map(async (id) => {
      const count = (missingCounts.get(id) ?? 0) + 1;
      missingCounts.set(id, count);
      if (count < 2) return;
      try {
        const response = await getJob(id);
        const subscribers = listeners.get(id);
        if (!subscribers) return;
        missingCounts.delete(id);
        subscribers.forEach((listener) => listener(response.data));
        if (TERMINAL_STATUSES.has(response.data.status)) listeners.delete(id);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          listeners.delete(id);
          missingCounts.delete(id);
        }
      }
    }),
  );
}

function onVisibilityChange(): void {
  if (document.visibilityState === 'visible' && listeners.size > 0) {
    window.clearTimeout(timer);
    void poll();
  }
}

export function subscribeJob(jobId: string, listener: Listener): () => void {
  let subscribers = listeners.get(jobId);
  if (!subscribers) {
    subscribers = new Set();
    listeners.set(jobId, subscribers);
  }
  subscribers.add(listener);
  missingCounts.delete(jobId);
  if (!visibilityBound) {
    document.addEventListener('visibilitychange', onVisibilityChange);
    visibilityBound = true;
  }
  if (listeners.size === 1) {
    window.clearTimeout(timer);
    void poll();
  }
  return () => {
    const current = listeners.get(jobId);
    if (!current) return;
    current.delete(listener);
    if (current.size === 0) listeners.delete(jobId);
    if (listeners.size === 0) {
      window.clearTimeout(timer);
      failures = 0;
    }
  };
}
