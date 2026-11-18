export interface Envelope<T> {
  code: string;
  message: string;
  data: T;
  request_id: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly data: unknown,
    public readonly requestId: string,
    public readonly retryAfter?: number,
  ) {
    super(message);
  }
}

const baseUrl: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const TIMEOUT_MS = 30_000;
const RETRY_DELAY_MS = 600;
const MAX_RETRY_DELAY_MS = 10_000;
const RETRYABLE_STATUS = new Set([429, 500, 502, 503, 504]);

const NETWORK_MESSAGE = '无法连接服务，请确认后端已启动后重试';
const TIMEOUT_MESSAGE = '请求超时，请稍后重试';
const BAD_RESPONSE_MESSAGE = '服务返回异常响应，请稍后重试';

// 页面上的轮询会并发发出多个请求；会话失效时只通知一次，避免反复卸载应用。
let sessionExpiredNotified = false;

export function resetSessionExpiredFlag(): void {
  sessionExpiredNotified = false;
}

function notifySessionExpired(path: string): void {
  if (sessionExpiredNotified) return;
  sessionExpiredNotified = true;
  window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { path } }));
}

function isRetryableMethod(method: string): boolean {
  return method === 'GET' || method === 'HEAD';
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function parseRetryAfterMs(value: string | null): number | undefined {
  if (!value) return undefined;
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) return undefined;
  return seconds * 1000;
}

function retryDelay(attempt: number, retryAfterMs?: number): number {
  const base = retryAfterMs ?? RETRY_DELAY_MS * 2 ** attempt;
  const jittered = base * (0.8 + Math.random() * 0.4);
  return Math.min(Math.max(jittered, 0), MAX_RETRY_DELAY_MS);
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
  attempt = 0,
): Promise<Envelope<T>> {
  const method = (options.method ?? 'GET').toUpperCase();
  const controller = new AbortController();
  let didTimeout = false;
  const timeout = window.setTimeout(() => {
    didTimeout = true;
    controller.abort();
  }, TIMEOUT_MS);
  options.signal?.addEventListener('abort', () => controller.abort(), { once: true });
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData) && !headers.has('content-type')) {
    headers.set('content-type', 'application/json');
  }
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers,
      credentials: 'same-origin',
      signal: controller.signal,
    });
    let body: Envelope<unknown>;
    try {
      body = (await response.json()) as Envelope<unknown>;
    } catch {
      if (isRetryableMethod(method) && attempt < 1) {
        await wait(RETRY_DELAY_MS);
        return api<T>(path, options, attempt + 1);
      }
      throw new ApiError(response.status, 'BAD_RESPONSE', BAD_RESPONSE_MESSAGE, null, '');
    }
    if (!response.ok) {
      // 只读请求遇到限流或短暂不可用：按 Retry-After（或指数退避）重试一次，
      // 避免页面把一次 429 当成永久失败。写请求不自动重试。
      if (
        isRetryableMethod(method)
        && RETRYABLE_STATUS.has(response.status)
        && attempt < 1
      ) {
        await wait(
          retryDelay(attempt, parseRetryAfterMs(response.headers.get('retry-after'))),
        );
        return api<T>(path, options, attempt + 1);
      }
      // 只有明确的会话/鉴权失效才请求重新登录；401 的瞬时抖动由 AuthGate 复核。
      if (
        response.status === 401
        && !path.startsWith('/auth/')
        && (body?.code === 'SESSION_EXPIRED' || body?.code === 'UNAUTHORIZED')
      ) {
        notifySessionExpired(path);
      }
      const retry = Number(response.headers.get('retry-after'));
      throw new ApiError(
        response.status,
        body?.code ?? 'HTTP_ERROR',
        body?.message ?? '服务暂时不可用，请稍后重试',
        body?.data ?? null,
        body?.request_id ?? '',
        retry || undefined,
      );
    }
    return body as Envelope<T>;
  } catch (caught) {
    if (caught instanceof ApiError) throw caught;
    const networkFailure = didTimeout || caught instanceof TypeError;
    if (networkFailure) {
      if (isRetryableMethod(method) && attempt < 1) {
        await wait(retryDelay(attempt));
        return api<T>(path, options, attempt + 1);
      }
      throw new ApiError(
        0,
        didTimeout ? 'REQUEST_TIMEOUT' : 'NETWORK_ERROR',
        didTimeout ? TIMEOUT_MESSAGE : NETWORK_MESSAGE,
        null,
        '',
      );
    }
    throw caught;
  } finally {
    window.clearTimeout(timeout);
  }
}
