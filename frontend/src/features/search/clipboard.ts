import type { TableInfo } from '../../services/search';

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** 生成可粘贴到 Word / Excel / WPS 的富文本表格，保留合并单元格。 */
export function tableToHtml(table: TableInfo): string {
  const caption = table.caption
    ? `<caption style="text-align:left;font-weight:600;padding:4px 0">${escapeHtml(table.caption)}</caption>`
    : '';
  const rows = table.rows
    .map((row, rowIndex) => {
      const cells = row
        .map((cell) => {
          const tag = rowIndex === 0 ? 'th' : 'td';
          const spans =
            (cell.rowspan > 1 ? ` rowspan="${cell.rowspan}"` : '') +
            (cell.colspan > 1 ? ` colspan="${cell.colspan}"` : '');
          const content = escapeHtml(cell.text).replace(/\r?\n/g, '<br>');
          return `<${tag}${spans}>${content}</${tag}>`;
        })
        .join('');
      return `<tr>${cells}</tr>`;
    })
    .join('');
  return (
    `<table border="1" cellspacing="0" cellpadding="4" ` +
    `style="border-collapse:collapse">${caption}<tbody>${rows}</tbody></table>`
  );
}

/** 纯文本兜底：题注 + 制表符分隔，粘贴到 Excel 也能分列。 */
export function tableToPlain(table: TableInfo): string {
  const lines = [
    ...(table.caption ? [table.caption] : []),
    ...table.rows.map((row) =>
      row.map((cell) => cell.text.replace(/[\t\r\n]+/g, ' ')).join('\t'),
    ),
  ];
  return lines.join('\n');
}

async function legacyCopy(text: string): Promise<void> {
  const area = document.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.style.position = 'fixed';
  area.style.top = '-1000px';
  area.style.opacity = '0';
  document.body.appendChild(area);
  area.select();
  try {
    if (!document.execCommand('copy')) throw new Error('clipboard unavailable');
  } finally {
    area.remove();
  }
}

/** 非安全上下文（局域网 http）没有 Clipboard API，用选中富文本节点复制。 */
async function legacyCopyRich(html: string): Promise<void> {
  const container = document.createElement('div');
  container.contentEditable = 'true';
  container.style.position = 'fixed';
  container.style.top = '-1000px';
  container.style.opacity = '0';
  container.innerHTML = html;
  document.body.appendChild(container);
  const selection = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(container);
  selection?.removeAllRanges();
  selection?.addRange(range);
  try {
    if (!document.execCommand('copy')) throw new Error('clipboard unavailable');
  } finally {
    selection?.removeAllRanges();
    container.remove();
  }
}

export async function copyPlainText(text: string): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    // 非安全上下文（局域网 http）会拒绝，走传统方式。
  }
  await legacyCopy(text);
}

export async function copyRichTable(table: TableInfo): Promise<void> {
  const html = tableToHtml(table);
  const plain = tableToPlain(table);
  const ClipboardCtor = (
    globalThis as {
      ClipboardItem?: new (items: Record<string, Blob>) => ClipboardItem;
    }
  ).ClipboardItem;
  try {
    if (ClipboardCtor && navigator.clipboard?.write) {
      await navigator.clipboard.write([
        new ClipboardCtor({
          'text/html': new Blob([html], { type: 'text/html' }),
          'text/plain': new Blob([plain], { type: 'text/plain' }),
        }),
      ]);
      return;
    }
  } catch {
    // 权限被拒时继续尝试传统富文本复制。
  }
  try {
    await legacyCopyRich(html);
    return;
  } catch {
    // 最后才退化为纯文本，保证复制按钮始终可用。
  }
  await copyPlainText(plain);
}
