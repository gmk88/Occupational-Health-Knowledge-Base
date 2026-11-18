import type { FormEvent } from 'react';
import { Button, TextField } from '../../components/ui';

export type Mode = 'semantic' | 'keyword' | 'hybrid';

export function SearchForm({ query, mode, busy, onQuery, onMode, onSubmit }: {
  query: string; mode: Mode; busy: boolean;
  onQuery: (value: string) => void; onMode: (value: Mode) => void; onSubmit: () => void;
}) {
  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit();
  }
  return (
    <form className="search-form" onSubmit={submit} role="search" autoComplete="off">
      {/* 不给 name：浏览器按字段名记忆输入历史，去掉后不会再弹出旧查询建议 */}
      <TextField label="查询" value={query} onChange={(event) => onQuery(event.target.value)} maxLength={512} autoComplete="off" spellCheck={false} />
      <label className="field"><span>模式</span><select value={mode} onChange={(event) => onMode(event.target.value as Mode)}>
        <option value="hybrid">混合</option><option value="semantic">语义</option><option value="keyword">关键词</option>
      </select></label>
      <Button type="submit" loading={busy}>
        {busy ? '检索中…' : '检索'}
      </Button>
    </form>
  );
}
