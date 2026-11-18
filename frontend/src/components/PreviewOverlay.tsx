import { useEffect, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

export function PreviewOverlay({
  title,
  onClose,
  children,
  actions,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  actions?: ReactNode;
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  return createPortal(
    <div
      className="preview-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <div className="preview-panel" onClick={(event) => event.stopPropagation()}>
        <div className="preview-head">
          <strong>{title}</strong>
          <div className="preview-head-actions">
            {actions}
            <button
              type="button"
              className="preview-close"
              onClick={onClose}
              aria-label="关闭预览"
            >
              关闭 ✕
            </button>
          </div>
        </div>
        <div className="preview-body">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
