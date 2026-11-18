import { useCallback, useEffect, useState } from 'react';
import { deleteDocument, listDocuments, reprocessDocument, type Document } from '../../services/documents';
import { Alert, Button } from '../../components/ui';

export function DocumentManagement({ onChanged }: { onChanged: () => void }) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [keyword, setKeyword] = useState('');

  const refresh = useCallback(async () => {
    const response = await listDocuments({ page_size: 100 });
    setDocuments(response.data.items);
  }, []);

  useEffect(() => {
    const id = window.setTimeout(() => void refresh().catch(() => {}), 0);
    return () => window.clearTimeout(id);
  }, [refresh]);

  async function run(fn: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await fn();
      // 组件持有自己的列表，必须一起刷新，否则删除后那一行仍在。
      await refresh();
      onChanged();
      setNotice(message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '操作失败');
    } finally {
      setBusy(false);
    }
  }

  if (documents.length === 0) return <p className="hint">暂无可管理的文档</p>;

  const query = keyword.trim().toLowerCase();
  const visible = query
    ? documents.filter((document) => document.title.toLowerCase().includes(query))
    : documents;

  return (
    <>
      {error && <Alert tone="danger">{error}</Alert>}
      {notice && <Alert tone="info">{notice}</Alert>}
      <div className="list-toolbar">
        <input
          className="list-search"
          type="search"
          autoComplete="off"
          spellCheck={false}
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="搜索文档标题"
          aria-label="搜索文档"
        />
        <span className="hint">{visible.length}/{documents.length}</span>
      </div>
      {visible.length === 0 ? (
        <p className="hint">没有匹配的文档</p>
      ) : (
        <ul className="document-list is-scrollable" aria-live="polite">
          {visible.map((document) => (
            <li key={document.id} className="document-item">
              <span>{document.title}</span>
              <span className="row">
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() => void run(() => reprocessDocument(document.id), '已提交重新处理，完成后需再次确认切分')}
                >
                  重处理
                </Button>
                <Button
                  variant="danger"
                  disabled={busy}
                  onClick={() => void run(
                    () => deleteDocument(document.id),
                    `已移除「${document.title}」及其检索索引`,
                  )}
                >
                  删除
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
