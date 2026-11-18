import { listPendingJobs } from './chunks';
import type { Job } from './jobs';

// 首页、导航角标、切分确认页共享同一个待确认轮询；页面隐藏时暂停，
// 失败时退避，避免常驻流量把限流额度吃满。
type Listener = (jobs: Job[]) => void;

const POLL_INTERVAL_MS = 30_000;
const MAX_BACKOFF_MS = 120_000;
const listeners = new Set<Listener>();
let cache: Job[] = [];
let timer = 0;
let inflight = false;
let failures = 0;
let visibilityBound = false;

function schedule(): void {
  if (listeners.size === 0) return;
  window.clearTimeout(timer);
  const delay = failures === 0
    ? POLL_INTERVAL_MS
    : Math.min(POLL_INTERVAL_MS * 2 ** failures, MAX_BACKOFF_MS);
  timer = window.setTimeout(() => void poll(), delay);
}

async function poll(): Promise<void> {
  if (inflight) return;
  if (document.visibilityState === 'hidden') {
    schedule();
    return;
  }
  inflight = true;
  try {
    cache = await listPendingJobs();
    listeners.forEach((listener) => listener(cache));
    failures = 0;
  } catch {
    failures = Math.min(failures + 1, 3);
  } finally {
    inflight = false;
    schedule();
  }
}

function onVisibilityChange(): void {
  if (document.visibilityState === 'visible' && listeners.size > 0) {
    window.clearTimeout(timer);
    void poll();
  }
}

export function refreshPendingJobs(): Promise<void> {
  if (inflight) return Promise.resolve();
  return poll();
}

export function subscribePendingJobs(listener: Listener): () => void {
  listeners.add(listener);
  listener(cache);
  if (!visibilityBound) {
    document.addEventListener('visibilitychange', onVisibilityChange);
    visibilityBound = true;
  }
  if (listeners.size === 1) {
    window.clearTimeout(timer);
    void poll();
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      window.clearTimeout(timer);
      failures = 0;
    }
  };
}
