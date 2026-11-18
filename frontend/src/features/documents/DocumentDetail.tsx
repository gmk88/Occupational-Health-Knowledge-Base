import { useState } from 'react';
import { Alert, Button, StatusBadge } from '../../components/ui';
import { updateDocumentMetadata, type Document } from '../../services/documents';

export function DocumentDetail({ document }: { document: Document }) {
  const initial = document.tags.map((tag) => tag.name).join(', ');
  const [tags, setTags] = useState(initial);
  const [saved, setSaved] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function saveTags() {
    const list = tags
      .split(/[,，]/)
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 50);
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const response = await updateDocumentMetadata(document.id, { tags: list });
      const next = response.data.tags.map((tag) => tag.name).join(', ');
      setTags(next);
      setSaved(next);
      setNotice('标签已保存');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '保存标签失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="detail-block" aria-label="文档详情">
      <div className="detail-block-head">
        <StatusBadge value={document.status} />
        <span className="hint">当前版本 v{document.current_version?.version_number ?? 1}</span>
      </div>
      <dl className="detail-list">
        <dt>原始文件</dt><dd>{document.original_filename ?? '—'}</dd>
        <dt>场景</dt><dd>{document.category?.name ?? '通用'}</dd>
        <dt>标签</dt><dd>{saved || '无'}</dd>
        <dt>来源</dt><dd>{document.source ?? '—'}</dd>
        <dt>备注</dt><dd>{document.notes ?? '—'}</dd>
      </dl>

      {error && <Alert tone="danger">{error}</Alert>}
      {notice && <Alert tone="info">{notice}</Alert>}

      <div className="tag-editor">
        <label className="field">
          <span>编辑标签（逗号分隔）</span>
          <input
            value={tags}
            autoComplete="off"
            spellCheck={false}
            maxLength={300}
            onChange={(event) => setTags(event.target.value)}
            aria-label="编辑文档标签"
          />
        </label>
        <Button variant="secondary" loading={busy} onClick={() => void saveTags()}>
          保存标签
        </Button>
      </div>
    </div>
  );
}
