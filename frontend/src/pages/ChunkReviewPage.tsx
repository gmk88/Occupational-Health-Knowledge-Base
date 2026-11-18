import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  CardGrid,
  CardStack,
  EmptyState,
  PageHeader,
  StatusBadge,
} from '../components/ui';
import { PreviewOverlay } from '../components/PreviewOverlay';
import {
  confirmChunks,
  deleteChunk,
  getChunks,
  mergeChunks,
  unmergeChunk,
  updateChunk,
  type ChunkItem,
  type ChunkReview,
} from '../services/chunks';
import { refreshPendingJobs, subscribePendingJobs } from '../services/pendingJobs';
import type { Job } from '../services/jobs';
import { jobDisplayName } from '../services/jobs';

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN');
}

export function ChunkReviewPage() {
  const [searchParams] = useSearchParams();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [review, setReview] = useState<ChunkReview | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [preview, setPreview] = useState<{
    title: string;
    text: string;
    header: string | null;
    html: string | null;
  } | null>(null);

  const refreshJobs = useCallback(() => refreshPendingJobs(), []);

  useEffect(() => subscribePendingJobs(setJobs), []);

  useEffect(() => {
    const fromUrl = searchParams.get('job');
    if (fromUrl && !selectedId) {
      setSelectedId(fromUrl);
    } else if (!selectedId && jobs[0]) {
      setSelectedId(jobs[0].id);
    }
  }, [jobs, searchParams, selectedId]);

  useEffect(() => {
    if (selectedId && jobs.length > 0 && !jobs.some((job) => job.id === selectedId)) {
      const first = jobs[0];
      if (first) setSelectedId(first.id);
    }
  }, [jobs, selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setReview(null);
      return;
    }
    let active = true;
    void getChunks(selectedId)
      .then((response) => {
        if (!active) return;
        setReview(response.data);
        setDrafts(
          Object.fromEntries(response.data.items.map((item) => [item.id, item.text])),
        );
        setSelected([]);
        setError('');
      })
      .catch((caught) => {
        if (active) setError(caught instanceof Error ? caught.message : '加载切分内容失败');
      });
    return () => { active = false; };
  }, [selectedId]);

  async function save(item: ChunkItem) {
    if (!selectedId) return;
    const text = drafts[item.id] ?? item.text;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const response = await updateChunk(selectedId, item.id, text);
      setReview((current) => current && ({
        ...current,
        items: current.items.map((chunk) =>
          chunk.id === item.id ? response.data : chunk,
        ),
      }));
      setNotice(`第 ${item.ordinal + 1} 个切分块已保存`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '保存失败');
    } finally {
      setBusy(false);
    }
  }

  async function remove(item: ChunkItem) {
    if (!selectedId) return;
    if (!window.confirm(`确定删除第 ${item.ordinal + 1} 个切分块？该内容将不会入库。`)) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await deleteChunk(selectedId, item.id);
      setReview((current) => current && ({
        ...current,
        items: current.items.filter((chunk) => chunk.id !== item.id),
      }));
      setNotice(`第 ${item.ordinal + 1} 个切分块已删除`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '删除失败');
    } finally {
      setBusy(false);
    }
  }

  function toggleSelect(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }

  async function applyMerge(chunkIds: string[], message: string) {
    if (!selectedId) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await mergeChunks(selectedId, chunkIds);
      const response = await getChunks(selectedId);
      setReview(response.data);
      setDrafts(
        Object.fromEntries(response.data.items.map((item) => [item.id, item.text])),
      );
      setSelected([]);
      setNotice(message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '合并失败');
    } finally {
      setBusy(false);
    }
  }

  async function mergeSelected() {
    if (!review) return;
    const selectedIds = review.items
      .filter((item) => selected.includes(item.id))
      .map((item) => item.id);
    if (selectedIds.length < 2) return;
    await applyMerge(selectedIds, `已合并 ${selectedIds.length} 个切分块`);
  }

  async function mergeWithNext(item: ChunkItem) {
    if (!review) return;
    const index = review.items.findIndex((chunk) => chunk.id === item.id);
    const next = review.items[index + 1];
    if (!next) return;
    await applyMerge([item.id, next.id], `已合并第 ${item.ordinal + 1}、${next.ordinal + 1} 个切分块`);
  }

  async function unmerge(item: ChunkItem) {
    if (!selectedId) return;
    if (!window.confirm(`撤销第 ${item.ordinal + 1} 个切分块的合并，恢复合并前的内容？`)) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await unmergeChunk(selectedId, item.id);
      const response = await getChunks(selectedId);
      setReview(response.data);
      setDrafts(
        Object.fromEntries(response.data.items.map((chunk) => [chunk.id, chunk.text])),
      );
      setSelected([]);
      setNotice('已撤销合并');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '撤销合并失败');
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!selectedId || !review) return;
    const name = jobDisplayName({
      filename: review.job.filename,
      document_title: review.job.document_title,
      document_id: review.job.document_id,
    });
    if (!window.confirm(`确认将「${name}」的 ${review.items.length} 个切分块向量化并入库？`)) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const response = await confirmChunks(selectedId);
      setNotice(`已确认 ${response.data.chunk_count} 个切分块，正在向量化入库`);
      setSelectedId(null);
      await refreshJobs();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '确认失败');
    } finally {
      setBusy(false);
    }
  }

  const tableCount = review?.items.filter((item) => item.block_type === 'table').length ?? 0;
  const selectedIndexes = review
    ? review.items
        .map((item, index) => (selected.includes(item.id) ? index : -1))
        .filter((index) => index >= 0)
    : [];
  const firstSelected = selectedIndexes[0] ?? -1;
  const lastSelected = selectedIndexes[selectedIndexes.length - 1] ?? -1;
  const canMergeSelected =
    selectedIndexes.length >= 2 &&
    lastSelected - firstSelected === selectedIndexes.length - 1;

  return (
    <main className="page chunk-review-page">
      <PageHeader
        eyebrow="WORKSPACE / 05"
        title="切分确认"
        description="预览并修改切分结果，确认后才会生成向量并写入检索索引。"
        meta={`${jobs.length} 个任务等待确认`}
      />

      {error && <Alert tone="danger">{error}</Alert>}
      {notice && <Alert tone="info">{notice}</Alert>}

      <CardGrid>
        <CardStack span={4}>
          <Card
            eyebrow="REVIEW / 01"
            title="待确认任务"
            description="切分已完成但尚未入库的文档"
          >
            {jobs.length === 0 ? (
              <EmptyState title="暂无待确认任务">
                上传文档并完成切分后，会在这里和首页提醒你确认。
              </EmptyState>
            ) : (
              <ul className="document-list" aria-live="polite">
                {jobs.map((job) => (
                  <li key={job.id}>
                    <button
                      className={`document-item${selectedId === job.id ? ' is-active' : ''}`}
                      onClick={() => { setSelectedId(job.id); setNotice(''); }}
                    >
                      <span className="document-item-head">
                        <strong>{jobDisplayName(job)}</strong>
                        <StatusBadge value={job.status} />
                      </span>
                      <span className="document-item-meta">
                        {`${job.total_pages} 页 · ${formatTime(job.created_at)}`}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </CardStack>

        <Card
          span={8}
          eyebrow="REVIEW / 02"
          title={review ? jobDisplayName({
            filename: review.job.filename,
            document_title: review.job.document_title,
            document_id: review.job.document_id,
          }) : '切分内容预览'}
          description="表格整表为一个切分块；确认前可逐块修改或删除。"
          actions={
            review ? (
              <Button
                loading={busy}
                disabled={!review.editable || review.items.length === 0}
                onClick={() => void confirm()}
              >
                确认并向量化入库
              </Button>
            ) : undefined
          }
        >
          {!review ? (
            <EmptyState title="未选择任务">从左侧选择一个待确认任务查看切分内容。</EmptyState>
          ) : review.items.length === 0 ? (
            <EmptyState title="没有切分块">请返回文档列表重新处理该文件。</EmptyState>
          ) : (
            <>
              <p className="hint chunk-review-summary">
                共 {review.items.length} 个切分块（整表 {tableCount} 个）
                {review.editable ? ' · 可编辑，确认后才会向量化入库' : ' · 该任务已确认，仅供查看'}
              </p>

              {review.editable && (
                <div className="chunk-merge-toolbar">
                  <span className="hint">已选 {selected.length} 个切分块</span>
                  <Button
                    variant="secondary"
                    loading={busy}
                    disabled={!canMergeSelected}
                    onClick={() => void mergeSelected()}
                  >
                    合并选中
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={busy || selected.length === 0}
                    onClick={() => setSelected([])}
                  >
                    清空选择
                  </Button>
                  <span className="hint">只能合并上下相邻的切分块</span>
                </div>
              )}

              {review.tables.length > 0 && (
                <div className="chunk-tables">
                  <div className="chunk-tables-head">
                    <strong>表格（{review.tables.length}）</strong>
                  </div>
                  <ul className="chunk-tables-list">
                    {review.tables.map((table, index) => (
                      <li key={table.table_id}>
                        <span className="chunk-table-label">
                          {table.section_title ?? `表格 ${index + 1}`}
                          <span className="hint">
                            {` · ${table.row_count} 行 · 第 ${table.page_start}${table.page_end !== table.page_start ? `-${table.page_end}` : ''} 页`}
                          </span>
                        </span>
                        {table.merged && <span className="chunk-merged">跨页合并</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <ul className="chunk-review-list">
                {review.items.map((item, index) => {
                  const dirty = (drafts[item.id] ?? item.text) !== item.text;
                  const previousTableId = review.items[index - 1]?.table_id ?? null;
                  const groupHead = item.table_id && item.table_id !== previousTableId;
                  const typeLabel = item.block_type === 'table' ? '表格' : '正文';
                  return (
                    <li key={item.id} className={groupHead ? 'chunk-group-start' : undefined}>
                      {groupHead && (
                        <p className="chunk-group-title">{item.section_title ?? '表格'}</p>
                      )}
                      <div className="chunk-item">
                      <div className="chunk-item-head">
                        {review.editable && (
                          <input
                            type="checkbox"
                            className="chunk-select"
                            checked={selected.includes(item.id)}
                            onChange={() => toggleSelect(item.id)}
                            aria-label={`选择第 ${item.ordinal + 1} 个切分块`}
                          />
                        )}
                        <span className="chunk-item-index">#{item.ordinal + 1}</span>
                        <span className={`chunk-type chunk-type-${item.block_type}`}>
                          {typeLabel}
                        </span>
                        <span className="hint">
                          {`第 ${item.page_start}${item.page_end !== item.page_start ? `-${item.page_end}` : ''} 页 · ${item.token_count} tokens`}
                        </span>
                        {item.is_edited && <span className="chunk-edited">已修改</span>}
                        {item.merged && <span className="chunk-merged">已合并</span>}
                        {dirty && <span className="chunk-dirty">未保存</span>}
                        <button
                          type="button"
                          className="preview-trigger is-inline"
                          onClick={() => setPreview({
                            title: `切分块 #${item.ordinal + 1} · 第 ${item.page_start}${item.page_end !== item.page_start ? `-${item.page_end}` : ''} 页`,
                            text: drafts[item.id] ?? item.text,
                            header: item.table_header,
                            html: item.table_html,
                          })}
                        >
                          放大预览
                        </button>
                      </div>
                      {item.table_header && (
                        <p className="hint chunk-table-header">表头上下文：{item.table_header}</p>
                      )}
                      {item.table_html && (
                        <details className="chunk-table-source">
                          <summary>查看解析器原始表格（含合并单元格）</summary>
                          <pre>{item.table_html}</pre>
                        </details>
                      )}
                      <textarea
                        className="chunk-text"
                        autoComplete="off"
                        spellCheck={false}
                        value={drafts[item.id] ?? item.text}
                        onChange={(event) => setDrafts((current) => ({
                          ...current,
                          [item.id]: event.target.value,
                        }))}
                        disabled={!review.editable || busy}
                        rows={item.block_type === 'table' ? 12 : 5}
                        aria-label={`第 ${item.ordinal + 1} 个切分块内容`}
                      />
                      {review.editable && (
                        <div className="chunk-item-actions">
                          <Button
                            variant="secondary"
                            loading={busy}
                            disabled={!dirty}
                            onClick={() => void save(item)}
                          >
                            保存修改
                          </Button>
                          <Button variant="danger" loading={busy} onClick={() => void remove(item)}>
                            删除此块
                          </Button>
                          {index < review.items.length - 1 && (
                            <Button
                              variant="secondary"
                              loading={busy}
                              onClick={() => void mergeWithNext(item)}
                            >
                              与下一块合并
                            </Button>
                          )}
                          {item.merged && (
                            <Button
                              variant="secondary"
                              loading={busy}
                              onClick={() => void unmerge(item)}
                            >
                              撤销合并
                            </Button>
                          )}
                        </div>
                      )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </Card>
      </CardGrid>

      {preview && (
        <PreviewOverlay title={preview.title} onClose={() => setPreview(null)}>
          {preview.header && <p className="hint">表头上下文：{preview.header}</p>}
          <pre className="preview-text">{preview.text}</pre>
          {preview.html && (
            <details className="chunk-table-source">
              <summary>解析器原始表格（含合并单元格）</summary>
              <pre>{preview.html}</pre>
            </details>
          )}
        </PreviewOverlay>
      )}
    </main>
  );
}
