import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, TextField } from '../../components/ui';
import {
  createAccessUser,
  listAccessUsers,
  resetUserPassword,
  updateAccessUser,
  type AccessUser,
} from '../../services/access';

function formatTime(value: string | null) {
  if (!value) return '从未登录';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN');
}

export function AccountManager() {
  const [users, setUsers] = useState<AccessUser[]>([]);
  const [loginName, setLoginName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<'admin' | 'viewer'>('viewer');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    const response = await listAccessUsers();
    setUsers(response.data);
  }, []);

  useEffect(() => {
    void load().catch((caught) =>
      setError(caught instanceof Error ? caught.message : '加载账号失败'),
    );
  }, [load]);

  async function submit() {
    if (!loginName.trim() || !password) {
      setError('请填写登录名与密码');
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await createAccessUser({
        login_name: loginName.trim(),
        display_name: displayName.trim() || loginName.trim(),
        password,
        role,
      });
      setLoginName('');
      setDisplayName('');
      setPassword('');
      setNotice('账号已创建');
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '创建账号失败');
    } finally {
      setBusy(false);
    }
  }

  async function toggleStatus(user: AccessUser) {
    setBusy(true);
    setError('');
    try {
      await updateAccessUser(user.id, {
        status: user.status === 'active' ? 'disabled' : 'active',
      });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '更新失败');
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(user: AccessUser) {
    setBusy(true);
    setError('');
    try {
      await updateAccessUser(user.id, {
        role: user.role === 'admin' ? 'viewer' : 'admin',
      });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '更新角色失败');
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword(user: AccessUser) {
    const next = window.prompt(`为「${user.display_name}」设置新密码（至少 8 位）`);
    if (!next) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await resetUserPassword(user.id, next);
      setNotice(`「${user.display_name}」的密码已重置，旧会话已失效`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '重置密码失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="access-panel">
      {error && <Alert tone="danger">{error}</Alert>}
      {notice && <Alert tone="info">{notice}</Alert>}

      <div className="access-create is-four">
        <TextField
          label="登录名"
          value={loginName}
          onChange={(event) => setLoginName(event.target.value)}
          autoComplete="off"
          maxLength={100}
        />
        <TextField
          label="显示名称"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          autoComplete="off"
          maxLength={100}
        />
        <TextField
          label="初始密码"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="new-password"
          maxLength={200}
        />
        <label className="field">
          <span>角色</span>
          <select value={role} onChange={(event) => setRole(event.target.value as 'admin' | 'viewer')}>
            <option value="viewer">只读</option>
            <option value="admin">管理员</option>
          </select>
        </label>
      </div>

      <div className="form-actions">
        <Button loading={busy} onClick={() => void submit()}>
          创建账号
        </Button>
      </div>

      <div className="access-table-wrap">
        <table className="access-table has-actions is-accounts">
          <thead>
            <tr>
              <th>账号</th>
              <th>角色</th>
              <th>状态</th>
              <th>最近登录</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>
                  <strong>{user.display_name}</strong>
                  <div className="hint">{user.login_name}</div>
                </td>
                <td>{user.role === 'admin' ? '管理员' : '只读'}</td>
                <td>
                  <span className={`access-status is-${user.status}`}>
                    {user.status === 'active' ? '启用' : user.status === 'locked' ? '锁定' : '停用'}
                  </span>
                </td>
                <td>{formatTime(user.last_login_at)}</td>
                <td>
                  <div className="access-actions">
                    <Button variant="secondary" loading={busy} onClick={() => void changeRole(user)}>
                      {user.role === 'admin' ? '降为只读' : '升为管理员'}
                    </Button>
                    <Button variant="secondary" loading={busy} onClick={() => void resetPassword(user)}>
                      重置密码
                    </Button>
                    <Button
                      variant={user.status === 'active' ? 'danger' : 'secondary'}
                      loading={busy}
                      onClick={() => void toggleStatus(user)}
                    >
                      {user.status === 'active' ? '停用' : '启用'}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
