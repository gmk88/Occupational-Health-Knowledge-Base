import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../services/http';
import { getLimitsCached, uploadDocument } from '../../services/documents';
import { JobProgress } from '../jobs/JobProgress';
import { Alert, Button, TextField } from '../../components/ui';

const DEFAULTS = { target: 512, max: 768, overlap: 64 };
const MAX_UPLOAD_RETRIES = 2;

async function uploadWithRetry(
  file: File,
  options: Parameters<typeof uploadDocument>[1],
) {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await uploadDocument(file, options);
    } catch (caught) {
      // 429 时按服务端 Retry-After 等待后重试当前文件；上传按 SHA256 幂等。
      if (caught instanceof ApiError && caught.status === 429 && attempt < MAX_UPLOAD_RETRIES) {
        const waitMs = Math.min((caught.retryAfter ?? 5) * 1000, 30_000);
        await new Promise((resolve) => window.setTimeout(resolve, waitMs));
        continue;
      }
      throw caught;
    }
  }
}

type ProcessingState = 'uploading' | 'processing' | 'duplicate' | 'failed';

interface ProcessingItem {
  key: string;
  filename: string;
  jobId: string | null;
  state: ProcessingState;
  message?: string;
}

const STATE_LABELS: Record<ProcessingState, string> = {
  uploading: '上传中',
  processing: '向量化中',
  duplicate: '重复跳过',
  failed: '失败',
};

const MODE_HINTS: Record<string, string> = {
  parent_child: '推荐：父块保留完整语义，子块按句子/表格行窗口检索；命中后返回父块，兼顾准确与完整。',
  fixed: '按固定长度窗口切分，长度均匀；可设置目标长度、上限与重叠。',
  structure: '一个段落一个切分块，不按长度聚合；可设置相邻块重叠。',
  sentence: '一个句子一个切分块，边界最清晰；可设置相邻块重叠。',
};

export function UploadForm({ onUploaded }: { onUploaded: () => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [title, setTitle] = useState('');
  const [tags, setTags] = useState('');
  const [chunkMode, setChunkMode] = useState('parent_child');
  const [target, setTarget] = useState(String(DEFAULTS.target));
  const [max, setMax] = useState(String(DEFAULTS.max));
  const [overlap, setOverlap] = useState(String(DEFAULTS.overlap));
  // 结构/句子模式默认不重叠，用户可显式设置。
  const [structureOverlap, setStructureOverlap] = useState('0');
  const [customParams, setCustomParams] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [limit, setLimit] = useState('');
  const [items, setItems] = useState<ProcessingItem[]>([]);
  const [uploadCount, setUploadCount] = useState({ done: 0, total: 0 });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isFixed = chunkMode === 'fixed';

  function clearFiles() {
    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    const targetNum = Number(target) || DEFAULTS.target;
    const maxNum = Number(max) || DEFAULTS.max;
    const overlapNum = overlap === '' ? DEFAULTS.overlap : Number(overlap) || 0;
    const naturalOverlap = structureOverlap === '' ? 0 : Number(structureOverlap) || 0;
    if (isFixed && customParams && !(0 <= overlapNum && overlapNum < targetNum && targetNum <= maxNum)) {
      setError('切分参数需满足：重叠 < 目标长度 ≤ 最大长度');
      setBusy(false);
      return;
    }
    if (!isFixed && !(0 <= naturalOverlap && naturalOverlap <= 4096)) {
      setError('重叠长度需在 0-4096 tokens 之间');
      setBusy(false);
      return;
    }
    const tagList = tags
      .split(/[,，]/)
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 50);
    setUploadCount({ done: 0, total: files.length });
    setItems(files.map((file) => ({
      key: `${file.name}-${file.lastModified}-${file.size}`,
      filename: file.name,
      jobId: null,
      state: 'uploading',
    })));
    let failures = 0;
    try {
      for (const file of files) {
        const key = `${file.name}-${file.lastModified}-${file.size}`;
        try {
          const result = await uploadWithRetry(file, {
            title: title || undefined,
            tags: tagList.length ? tagList : undefined,
            chunk_mode: chunkMode,
            // 父子块使用服务端推荐参数；固定/结构/句子按表单提交。
            ...(chunkMode === 'parent_child'
              ? {}
              : isFixed
                ? customParams
                  ? {
                      chunk_target_tokens: targetNum,
                      chunk_max_tokens: maxNum,
                      chunk_overlap_tokens: overlapNum,
                    }
                  : {}
                : { chunk_overlap_tokens: naturalOverlap }),
          });
          setItems((prev) => prev.map((item) => item.key === key ? {
            ...item,
            jobId: result.job_id,
            state: result.job_id ? 'processing' : 'duplicate',
          } : item));
        } catch (caught) {
          failures += 1;
          setItems((prev) => prev.map((item) => item.key === key ? {
            ...item,
            state: 'failed',
            message: caught instanceof Error ? caught.message : '上传失败',
          } : item));
        } finally {
          setUploadCount((prev) => ({ ...prev, done: prev.done + 1 }));
        }
      }
      clearFiles();
      setTitle('');
      setTags('');
      if (failures > 0) setError(`${failures} 个文件上传失败，可稍后重试`);
      onUploaded();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '上传失败');
    } finally {
      setBusy(false);
      setUploadCount({ done: 0, total: 0 });
    }
  }

  useEffect(() => {
    let active = true;
    getLimitsCached()
      .then((response) => {
        if (!active) return;
        setLimit(
          `支持 PDF / Word / TXT / Markdown；单文件 ${Math.round(response.data.max_file_size_bytes / 1048576)} MiB、`
          + `${response.data.max_pages_per_file} 页、批量 ${response.data.max_files_per_web_batch} 个、`
          + `每分钟最多 ${response.data.upload_limit_per_minute} 次上传`,
        );
      })
      .catch(() => { /* 限额提示失败不影响上传 */ });
    return () => { active = false; };
  }, []);

  return (
    <form
      className="upload-form"
      onSubmit={(event) => void submit(event)}
      autoComplete="off"
      aria-describedby={error ? 'upload-error' : undefined}
    >
      {limit && <p className="hint upload-limit" role="status">{limit}</p>}
      {error && <Alert tone="danger" id="upload-error">{error}</Alert>}

      <div className="form-row">
        <TextField
          label="标题（可选）"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={300}
          autoComplete="off"
          spellCheck={false}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? 'upload-error' : undefined}
        />
        <label className="field">
          <span>文件</span>
          <input
            ref={fileInputRef}
            type="file"
            autoComplete="off"
            accept=".pdf,.docx,.txt,.md,.markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
            multiple
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? 'upload-error' : undefined}
            required
          />
        </label>
      </div>

      {files.length > 0 && (
        <p className="hint upload-selected">
          已选择 {files.length} 个文件：
          {files.slice(0, 5).map((file) => file.name).join('、')}
          {files.length > 5 ? ' 等' : ''}
          <button type="button" className="link-button" onClick={clearFiles}>
            清空选择
          </button>
        </p>
      )}

      <TextField
        label="标签（可选）"
        value={tags}
        onChange={(event) => setTags(event.target.value)}
        maxLength={300}
        autoComplete="off"
        spellCheck={false}
      />
      <p className="hint">多个标签用逗号分隔；系统不会再自动添加标签。</p>

      <fieldset className="field chunk-settings">
        <legend>切分设置</legend>
        <label className="field">
          <span>切分方式</span>
          <select value={chunkMode} onChange={(event) => setChunkMode(event.target.value)}>
            <option value="parent_child">语义父子块（推荐）</option>
            <option value="fixed">固定大小切分</option>
            <option value="structure">按结构（段落）切分</option>
            <option value="sentence">按句子切分</option>
          </select>
        </label>
        <p className="hint">{MODE_HINTS[chunkMode]}</p>
        {isFixed ? (
          <>
            <label className="check">
              <input
                type="checkbox"
                checked={customParams}
                onChange={(event) => setCustomParams(event.target.checked)}
              />
              <span>自定义切分参数（默认：目标 {DEFAULTS.target} / 上限 {DEFAULTS.max} / 重叠 {DEFAULTS.overlap}）</span>
            </label>
            {customParams && (
              <div className="chunk-params">
                <label className="field">
                  <span>目标长度（tokens）</span>
                  <input type="number" autoComplete="off" min={64} max={8192} value={target} onChange={(event) => setTarget(event.target.value)} />
                  <small className="hint">每个块尽量达到的长度。</small>
                </label>
                <label className="field">
                  <span>最大长度（tokens）</span>
                  <input type="number" autoComplete="off" min={128} max={16384} value={max} onChange={(event) => setMax(event.target.value)} />
                  <small className="hint">任何块都不会超过该长度。</small>
                </label>
                <label className="field">
                  <span>重叠长度（tokens）</span>
                  <input type="number" autoComplete="off" min={0} max={4096} value={overlap} onChange={(event) => setOverlap(event.target.value)} />
                  <small className="hint">相邻块之间重复的内容量，需小于目标长度。</small>
                </label>
              </div>
            )}
          </>
        ) : chunkMode === 'parent_child' ? null : (
          <div className="chunk-params">
            <label className="field">
              <span>重叠长度（tokens）</span>
              <input
                type="number"
                autoComplete="off"
                min={0}
                max={4096}
                value={structureOverlap}
                onChange={(event) => setStructureOverlap(event.target.value)}
              />
              <small className="hint">
                下一块开头重复上一块结尾的内容，0 表示不重叠；表格会打断重叠链。
              </small>
            </label>
          </div>
        )}
      </fieldset>

      <div className="form-actions">
        <Button type="submit" loading={busy}>
          {busy ? `正在上传 ${uploadCount.done}/${uploadCount.total}…` : '开始上传'}
        </Button>
      </div>

      {items.length > 0 && (
        <div className="upload-jobs" aria-live="polite">
          {items.map((item) => (
            <div key={item.key}>
              {item.state === 'processing' && item.jobId ? (
                <JobProgress jobId={item.jobId} filename={item.filename} onSettled={onUploaded} />
              ) : (
                <div className={`upload-job${item.state === 'failed' ? ' is-failed' : ''}`}>
                  <div className="upload-job-head">
                    <span className="upload-job-name">{item.filename}</span>
                    <span className="upload-job-status" data-state={item.state}>{STATE_LABELS[item.state]}</span>
                  </div>
                  <p className="hint upload-job-detail">
                    {item.state === 'uploading'
                      ? '文件传输中，完成后立即开始向量化…'
                      : item.state === 'duplicate'
                        ? '内容与已有文档重复，已跳过向量化。'
                        : item.message ?? '处理失败。'}
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </form>
  );
}
