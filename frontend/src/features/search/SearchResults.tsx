import { useEffect, useRef, useState } from 'react';
import type { SearchResult, TableInfo } from '../../services/search';
import { copyPlainText, copyRichTable } from './clipboard';
import { SourceLink } from './SourceLink';
import { EmptyState } from '../../components/ui';
import { PreviewOverlay } from '../../components/PreviewOverlay';

interface PreviewState {
  title: string;
  table?: TableInfo;
  text?: string;
}

type CopyState = 'idle' | 'copied' | 'failed';

function CopyButton({
  label,
  hint,
  onCopy,
}: {
  label: string;
  hint?: string;
  onCopy: () => Promise<void>;
}) {
  const [state, setState] = useState<CopyState>('idle');
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function handle() {
    try {
      await onCopy();
      setState('copied');
    } catch {
      setState('failed');
    }
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState('idle'), 2000);
  }

  const text = state === 'copied' ? '已复制' : state === 'failed' ? '复制失败' : label;
  return (
    <button
      type="button"
      className={`preview-trigger copy-trigger${state === 'copied' ? ' is-copied' : ''}${state === 'failed' ? ' is-failed' : ''}`}
      onClick={() => void handle()}
      title={hint}
      aria-label={hint ?? label}
      aria-live="polite"
    >
      {text}
    </button>
  );
}

function TableView({ table }: { table: TableInfo }) {
  if (table.rows.length === 0) return <p>{table.header ?? '表格内容为空'}</p>;
  return (
    <div className="result-table table-view">
      <div className="result-table-scroll">
        <table>
          <tbody>
            {table.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  rowIndex === 0 ? (
                    <th key={cellIndex} rowSpan={cell.rowspan} colSpan={cell.colspan}>
                      {cell.text}
                    </th>
                  ) : (
                    <td key={cellIndex} rowSpan={cell.rowspan} colSpan={cell.colspan}>
                      {cell.text}
                    </td>
                  )
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TableResult({ table, onExpand }: { table: TableInfo; onExpand: () => void }) {
  return (
    <div className="result-table">
      <div className="result-table-head">
        {table.caption && <p className="result-table-caption">{table.caption}</p>}
        <div className="result-actions">
          <CopyButton
            label="复制表格"
            hint="复制为带格式的表格，粘贴到 Word / Excel 保留合并单元格"
            onCopy={() => copyRichTable(table)}
          />
          <button type="button" className="preview-trigger" onClick={onExpand}>
            放大预览
          </button>
        </div>
      </div>
      <TableView table={table} />
      <p className="hint">整表共 {table.total_rows} 行</p>
    </div>
  );
}

export function SearchResults({ results, degraded, tookMs }: { results: SearchResult[]; degraded: boolean; tookMs: number }) {
  const [preview, setPreview] = useState<PreviewState | null>(null);

  if (results.length === 0) {
    return (
      <EmptyState title="还没有检索结果">
        输入关键词并点击检索；可尝试更换词语、放宽过滤条件或切换检索模式。
      </EmptyState>
    );
  }
  return (
    <section className="search-results" aria-label="检索结果" aria-live="polite">
      {degraded && <p className="hint">当前为降级模式，仅部分召回源可用。</p>}
      <p className="hint" role="status">
        共 {results.length} 条，耗时 {tookMs} ms
      </p>
      <ol className="result-list">
        {results.map((result, index) => (
          <li key={result.chunk_id} className="result-row">
            <span className="result-index" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
            <div className="result-main">
              <h3>
                {result.document_name} · 第 {result.page_start}
                {result.page_end !== result.page_start ? `-${result.page_end}` : ''} 页
                {result.kind === 'table' && <span className="result-kind">表格</span>}
              </h3>
              {result.kind === 'table' && result.table ? (
                <TableResult
                  table={result.table}
                  onExpand={() => setPreview({
                    title: `表格预览 · ${result.document_name} · 第 ${result.page_start} 页`,
                    table: result.table ?? undefined,
                  })}
                />
              ) : (
                <div className="result-text-block">
                  <p>{result.text}</p>
                  <div className="result-actions">
                    <CopyButton
                      label="复制正文"
                      hint="复制该正文块的完整文本"
                      onCopy={() => copyPlainText(result.text)}
                    />
                    <button
                      type="button"
                      className="preview-trigger"
                      onClick={() => setPreview({
                        title: `正文预览 · ${result.document_name} · 第 ${result.page_start} 页`,
                        text: result.text,
                      })}
                    >
                      放大预览
                    </button>
                  </div>
                </div>
              )}
              <p className="hint">RRF {result.scores.rrf.toFixed(4)} · {result.recall_sources.join('+')}</p>
            </div>
            <div className="result-link">
              <SourceLink
                documentId={result.document_id}
                page={result.page_start}
                pageEnd={result.page_end}
                chunkId={result.chunk_id}
              />
            </div>
          </li>
        ))}
      </ol>

      {preview && (
        <PreviewOverlay
          title={preview.title}
          onClose={() => setPreview(null)}
          actions={preview.table ? (
            <CopyButton
              label="复制表格"
              hint="复制为带格式的表格，粘贴到 Word / Excel 保留合并单元格"
              onCopy={() => copyRichTable(preview.table as TableInfo)}
            />
          ) : (
            <CopyButton
              label="复制正文"
              hint="复制完整正文"
              onCopy={() => copyPlainText(preview.text ?? '')}
            />
          )}
        >
          {preview.table ? (
            <TableView table={preview.table} />
          ) : (
            <pre className="preview-text">{preview.text}</pre>
          )}
        </PreviewOverlay>
      )}
    </section>
  );
}
