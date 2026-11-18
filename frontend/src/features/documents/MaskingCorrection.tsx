import { useState } from 'react';
import { api } from '../../services/http';
import { Button } from '../../components/ui';

export function MaskingCorrection({ documentId }: { documentId: string }) {
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState<number | null>(null);

  async function submit() {
    setBusy(true);
    try {
      const response = await api<{ masking_revision: number }>(`/documents/${documentId}/masking-corrections`, { method: 'POST' });
      setRevision(response.data.masking_revision);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="detail-block">
      <Button disabled={busy} onClick={() => void submit()}>应用修正</Button>
      {revision != null && <p className="hint">当前 masking revision：{revision}</p>}
    </div>
  );
}
