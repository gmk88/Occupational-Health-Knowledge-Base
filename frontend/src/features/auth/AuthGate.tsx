import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api, ApiError, resetSessionExpiredFlag } from '../../services/http';
import { Alert, Button, TextField } from '../../components/ui';

export type ActorType = 'user' | 'api_client';
export type Role = 'admin' | 'viewer' | 'service';
export interface Principal {
  id: string;
  name: string;
  actor_type: ActorType;
  role: Role;
  scopes: string[];
  session_expires_at: string | null;
}

export function AuthGate({ children }: { children: (principal: Principal) => ReactNode }) {
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [loginFailed, setLoginFailed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const load = useCallback(async () => {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const response = await api<Principal>('/auth/me');
        setPrincipal(response.data);
        setError('');
        resetSessionExpiredFlag();
        setLoading(false);
        return;
      } catch (caught) {
        // 401 是正常未登录状态，直接显示登录页；网络抖动只短暂重试一次。
        if (caught instanceof ApiError && caught.status === 401) {
          setLoading(false);
          return;
        }
        if (attempt < 1) {
          await new Promise((resolve) => window.setTimeout(resolve, 700));
          continue;
        }
        setError(caught instanceof Error ? caught.message : '暂时无法验证会话，请重试。');
      }
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    const id = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(id);
  }, [load]);

  useEffect(() => {
    const onUnauthorized = () => {
      // 先静默复核：并发轮询里的偶发 401 不该把用户踢出正在操作的页面。
      void (async () => {
        try {
          const response = await api<Principal>('/auth/me');
          setPrincipal(response.data);
          setError('');
          resetSessionExpiredFlag();
          return;
        } catch (verify) {
          if (!(verify instanceof ApiError) || verify.status !== 401) {
            resetSessionExpiredFlag();
            return;
          }
        }
        window.sessionStorage.setItem(
          'oh:returnTo',
          `${window.location.pathname}${window.location.search}`,
        );
        setPrincipal(null);
        setError('会话已过期，请重新登录');
      })();
    };
    window.addEventListener('auth:unauthorized', onUnauthorized);
    return () => window.removeEventListener('auth:unauthorized', onUnauthorized);
  }, []);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    setLoginFailed(false);
    const form = new FormData(event.currentTarget);
    try {
      const response = await api<Principal>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ login_name: form.get('login_name'), password: form.get('password') }),
      });
      setPrincipal(response.data);
      resetSessionExpiredFlag();
      const saved = window.sessionStorage.getItem('oh:returnTo');
      window.sessionStorage.removeItem('oh:returnTo');
      const returnTo = (location.state as { from?: string } | null)?.from ?? saved ?? '/';
      void navigate(returnTo, { replace: true });
    } catch (caught) {
      setLoginFailed(true);
      setError(caught instanceof Error ? caught.message : '登录失败，请重试。');
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <main className="centered" aria-live="polite" aria-busy="true">
        正在恢复安全会话…
      </main>
    );
  }
  if (!principal) {
    return (
      <main className="login-layout">
        <section className="login-panel" aria-labelledby="login-title">
          <p className="eyebrow">OCCUPATIONAL HEALTH</p>
          <h1 id="login-title">职业健康知识库</h1>
          <p>登录后检索专业资料，或由管理员维护文档与处理质量。</p>
          {error && (
            <Alert tone="danger" id="login-error">
              {error}
            </Alert>
          )}
          <form onSubmit={(event) => void login(event)} aria-describedby={error ? 'login-error' : undefined}>
            <TextField
              label="账号"
              name="login_name"
              autoComplete="username"
              required
              maxLength={100}
              aria-invalid={loginFailed ? true : undefined}
              aria-describedby={error ? 'login-error' : undefined}
            />
            <TextField
              label="密码"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={1024}
              aria-invalid={loginFailed ? true : undefined}
              aria-describedby={error ? 'login-error' : undefined}
            />
            <Button type="submit" loading={submitting}>
              {submitting ? '正在登录…' : '安全登录'}
            </Button>
          </form>
        </section>
      </main>
    );
  }
  return <>{children(principal)}</>;
}
