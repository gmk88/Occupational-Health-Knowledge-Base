import {
  forwardRef,
  useEffect,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
} from 'react';

export function Button({
  variant = 'primary',
  className = '',
  type = 'button',
  loading = false,
  disabled,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'danger';
  loading?: boolean;
}) {
  return (
    <button
      type={type}
      className={`button button-${variant} ${className}`}
      aria-busy={loading || undefined}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <span className="button-spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}

export const TextField = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string }
>(function TextField(
  { label, id, error, 'aria-describedby': describedBy, ...props },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? props.name ?? generatedId;
  const errorId = `${inputId}-error`;
  const description = [describedBy, error ? errorId : undefined].filter(Boolean).join(' ') || undefined;
  return (
    <label className="field" htmlFor={inputId}>
      <span>{label}</span>
      <input
        ref={ref}
        id={inputId}
        // 默认关闭浏览器自动填充/历史建议，避免清空输入框时弹出历史下拉；
        // 调用方（如登录页）仍可显式传入 autoComplete 覆盖。
        autoComplete="off"
        aria-invalid={error ? true : undefined}
        aria-describedby={description}
        {...props}
      />
      {error && (
        <span className="field-error" id={errorId} role="alert">
          {error}
        </span>
      )}
    </label>
  );
});

export function Alert({
  tone = 'info',
  id,
  children,
}: {
  tone?: 'info' | 'danger' | 'warning';
  id?: string;
  children: ReactNode;
}) {
  return (
    <div
      id={id}
      className={`alert alert-${tone}`}
      role={tone === 'danger' ? 'alert' : 'status'}
    >
      {children}
    </div>
  );
}

const STATUS_LABELS: Record<string, string> = {
  searchable: '可检索',
  processing: '处理中',
  needs_review: '需复核',
  deleted: '已删除',
  current: '当前版本',
  replaced: '已替换',
  failed: '失败',
  cancelled: '已取消',
  partial_success: '部分成功',
  queued: '排队中',
  parsing: '解析中',
  embedding: '向量化中',
  pending_confirmation: '待确认切分',
  completed: '已完成',
  pending: '待处理',
  empty: '空页',
  low_quality: '低质量',
  text_layer: '文本层',
  ocr: 'OCR',
  mixed: '混合',
  up: '正常',
  down: '异常',
  ready: '就绪',
  degraded: '降级',
  not_ready: '未就绪',
  active: '正常',
  disabled: '已停用',
  locked: '已锁定',
  admin: '管理员',
  viewer: '普通使用者',
};

const STATUS_TONES: Record<string, string> = {
  searchable: 'searchable',
  completed: 'completed',
  current: 'current',
  up: 'up',
  ready: 'ready',
  processing: 'processing',
  queued: 'queued',
  parsing: 'parsing',
  embedding: 'embedding',
  pending: 'pending',
  needs_review: 'needs_review',
  partial_success: 'partial_success',
  degraded: 'degraded',
  failed: 'failed',
  cancelled: 'cancelled',
  disabled: 'disabled',
  locked: 'locked',
  down: 'down',
  not_ready: 'not_ready',
};

export function StatusBadge({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  const label = STATUS_LABELS[normalized] ?? value;
  const tone = STATUS_TONES[normalized] ?? 'neutral';
  return (
    <span className={`status status-${tone}`} title={value}>
      {label}
    </span>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <section className="empty-state" aria-live="polite">
      <h2>{title}</h2>
      {children && <p>{children}</p>}
    </section>
  );
}

export function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
}) {
  return (
    <nav className="pagination" aria-label="分页">
      <Button variant="secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        上一页
      </Button>
      <span>
        第 {page} / {Math.max(totalPages, 1)} 页
      </span>
      <Button
        variant="secondary"
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
      >
        下一页
      </Button>
    </nav>
  );
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function ConfirmDialog({
  title,
  description,
  confirmLabel = '确认',
  busy = false,
  onConfirm,
  onCancel,
}: {
  title: string;
  description: string;
  confirmLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const cancelRef = useRef(onCancel);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    cancelRef.current = onCancel;
  }, [onCancel]);

  useEffect(() => {
    previousFocus.current = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    const focusables = () =>
      dialog
        ? Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
            (element) => element.getAttribute('aria-hidden') !== 'true',
          )
        : [];
    (focusables()[0] ?? dialog)?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        cancelRef.current();
        return;
      }
      if (event.key !== 'Tab') return;
      const elements = focusables();
      if (elements.length === 0) {
        event.preventDefault();
        dialog?.focus();
        return;
      }
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus.current?.focus();
    };
  }, []);

  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <section
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        ref={dialogRef}
      >
        <h2 id={titleId}>{title}</h2>
        <p id={descriptionId}>{description}</p>
        <div className="dialog-actions">
          <Button variant="secondary" onClick={onCancel}>
            取消
          </Button>
          <Button variant="danger" disabled={busy} onClick={onConfirm}>
            {busy ? '处理中…' : confirmLabel}
          </Button>
        </div>
      </section>
    </div>
  );
}

/* ===== 大卡片布局系统 ===== */

type CardSpan = 3 | 4 | 5 | 6 | 7 | 8 | 9 | 12;

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  meta,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  meta?: string;
}) {
  return (
    <header className="page-head">
      <div className="page-head-main">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-head-desc">{description}</p>}
      </div>
      {(actions || meta) && (
        <div className="page-head-side">
          {actions}
          {meta && <p className="page-head-meta">{meta}</p>}
        </div>
      )}
    </header>
  );
}

export function CardGrid({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`card-grid ${className}`}>{children}</div>;
}

export function CardStack({
  span = 5,
  children,
  className = '',
}: {
  span?: CardSpan;
  children: ReactNode;
  className?: string;
}) {
  return <div className={`card-stack span-${span} ${className}`}>{children}</div>;
}

export function Card({
  eyebrow,
  title,
  description,
  actions,
  span = 12,
  tone = 'default',
  className = '',
  bodyClassName = '',
  id,
  children,
}: {
  eyebrow?: string;
  title?: string;
  description?: string;
  actions?: ReactNode;
  span?: CardSpan;
  tone?: 'default' | 'accent' | 'muted';
  className?: string;
  bodyClassName?: string;
  id?: string;
  children: ReactNode;
}) {
  const generatedId = useId();
  const headingId = `${id ?? generatedId}-title`;
  return (
    <section
      id={id}
      className={`card card-${tone} span-${span} ${className}`}
      aria-labelledby={title ? headingId : undefined}
    >
      {(eyebrow || title || description || actions) && (
        <header className="card-head">
          <div className="card-head-text">
            {eyebrow && <p className="card-eyebrow">{eyebrow}</p>}
            {title && <h2 className="card-title" id={headingId}>{title}</h2>}
            {description && <p className="card-desc">{description}</p>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      <div className={`card-body ${bodyClassName}`}>{children}</div>
    </section>
  );
}

export function CardSection({
  title,
  description,
  actions,
  children,
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card-section">
      {(title || description || actions) && (
        <header className="card-section-head">
          <div>
            {title && <h3 className="card-section-title">{title}</h3>}
            {description && <p className="card-section-desc">{description}</p>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Metric({
  label,
  value,
  hint,
  emphasis = false,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  emphasis?: boolean;
}) {
  return (
    <div className={`metric${emphasis ? ' is-emphasis' : ''}`}>
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      {hint && <span className="metric-hint">{hint}</span>}
    </div>
  );
}
