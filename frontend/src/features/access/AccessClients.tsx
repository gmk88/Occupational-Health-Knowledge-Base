import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, TextField } from '../../components/ui';
import {
  createAccessClient,
  listAccessClients,
  listScopes,
  rotateAccessKey,
  updateAccessClient,
  type AccessClient,
} from '../../services/access';

function formatTime(value: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN');
}

export function AccessClients() {
  const [clients, setClients] = useState<AccessClient[]>([]);
  const [scopes, setScopes] = useState<string[]>([]);
  const [name, setName] = useState('');
  const [selectedScopes, setSelectedScopes] = useState<string[]>(['search:read']);
  const [limit, setLimit] = useState('60');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [newKey, setNewKey] = useState('');

  const load = useCallback(async () => {
    const [clientRes, scopeRes] = await Promise.all([listAccessClients(), listScopes()]);
    setClients(clientRes.data);
    setScopes(scopeRes.data);
  }, []);

  useEffect(() => {
    void load().catch((caught) =>
      setError(caught instanceof Error ? caught.message : '加载接入方失败'),
    );
  }, [load]);

  function toggleScope(scope: string) {
    setSelectedScopes((current) =>
      current.includes(scope)
        ? current.filter((item) => item !== scope)
        : [...current, scope],
    );
  }

  async function submit() {
    if (!name.trim()) {
      setError('请填写接入方名称');
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    setNewKey('');
    try {
      const response = await createAccessClient({
        name: name.trim(),
        scopes: selectedScopes,
        rate_limit_per_minute: Number(limit) || 60,
      });
      setNewKey(response.data.key ?? '');
      setName('');
      setNotice(`已创建接入方「${response.data.name}」`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '创建失败');
    } finally {
      setBusy(false);
    }
  }

  async function rotate(client: AccessClient) {
    if (!window.confirm(`为「${client.name}」生成新密钥？旧密钥会立即失效。`)) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const response = await rotateAccessKey(client.id);
      setNewKey(response.data.key ?? '');
      setNotice(`「${client.name}」的密钥已轮换`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '轮换失败');
    } finally {
      setBusy(false);
    }
  }

  async function toggleStatus(client: AccessClient) {
    setBusy(true);
    setError('');
    try {
      await updateAccessClient(client.id, {
        status: client.status === 'active' ? 'disabled' : 'active',
      });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '更新失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="access-panel">
      {error && <Alert tone="danger">{error}</Alert>}
      {notice && <Alert tone="info">{notice}</Alert>}
      {newKey && (
        <Alert tone="warning">
          <span>新密钥只显示这一次，请立即复制保存：</span>
          <code className="access-key">{newKey}</code>
        </Alert>
      )}

      <div className="access-create is-four is-clients">
        <TextField
          label="接入方名称"
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={100}
          autoComplete="off"
        />
        <label className="field">
          <span>每分钟限额</span>
          <input
            type="number"
            autoComplete="off"
            min={1}
            max={6000}
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
          />
        </label>
      </div>

      <fieldset className="access-scopes">
        <legend>权限范围</legend>
        {scopes.map((scope) => (
          <label className="check" key={scope}>
            <input
              type="checkbox"
              checked={selectedScopes.includes(scope)}
              onChange={() => toggleScope(scope)}
            />
            <span>{scope}</span>
          </label>
        ))}
      </fieldset>

      <div className="form-actions">
        <Button loading={busy} onClick={() => void submit()}>
          创建接入方
        </Button>
      </div>

      {clients.length === 0 ? (
        <p className="hint">还没有接入方，创建后把密钥交给对方即可。</p>
      ) : (
        <div className="access-table-wrap">
          <table className="access-table has-actions is-clients">
            <thead>
              <tr>
                <th>接入方</th>
                <th>状态</th>
                <th>密钥前缀</th>
                <th>限额/分钟</th>
                <th>最近调用</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((client) => (
                <tr key={client.id}>
                  <td>
                    <strong>{client.name}</strong>
                    <div className="hint">{client.scopes.join('、')}</div>
                  </td>
                  <td>
                    <span className={`access-status is-${client.status}`}>
                      {client.status === 'active' ? '启用' : '停用'}
                    </span>
                  </td>
                  <td>
                    <code>{client.key_prefix ?? '—'}</code>
                    <div className="hint">{client.active_key_count} 个可用密钥</div>
                  </td>
                  <td>{client.rate_limit_per_minute}</td>
                  <td>{formatTime(client.last_used_at)}</td>
                  <td>
                    <div className="access-actions">
                      <Button
                        variant="secondary"
                        loading={busy}
                        onClick={() => void rotate(client)}
                      >
                        轮换密钥
                      </Button>
                      <Button
                        variant={client.status === 'active' ? 'danger' : 'secondary'}
                        loading={busy}
                        onClick={() => void toggleStatus(client)}
                      >
                        {client.status === 'active' ? '停用' : '启用'}
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
