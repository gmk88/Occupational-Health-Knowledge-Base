import { useState } from 'react';
import { getQualityReport } from '../../services/documents';
import { Button } from '../../components/ui';

export function QualityExport({ documentId }: { documentId: string }) {
  const [busy, setBusy] = useState(false);

  async function exportJson() {
    setBusy(true);
    try {
      const response = await getQualityReport(documentId);
      const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `quality-${documentId}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } finally {
      setBusy(false);
    }
  }

  return <Button variant="secondary" disabled={busy} onClick={() => void exportJson()}>导出质量报告</Button>;
}
