import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  copyPlainText,
  copyRichTable,
  tableToHtml,
  tableToPlain,
} from './clipboard';
import type { TableInfo } from '../../services/search';

const table: TableInfo = {
  id: 't1',
  caption: '表 1 职业接触限值',
  header: '| 物质 | 限值 |',
  total_rows: 2,
  rows: [
    [
      { text: '物质', rowspan: 2, colspan: 1 },
      { text: '<限值>', rowspan: 1, colspan: 2 },
    ],
    [
      { text: '苯', rowspan: 1, colspan: 1 },
      { text: '6', rowspan: 1, colspan: 1 },
      { text: '10', rowspan: 1, colspan: 1 },
    ],
  ],
};

class FakeClipboardItem {
  constructor(public readonly items: Record<string, Blob>) {}
}

// jsdom 的 Blob 没有 text()，用轻量替身读取写入内容。
class FakeBlob {
  constructor(public readonly parts: string[], public readonly type: string) {}
  async text(): Promise<string> {
    return this.parts.join('');
  }
}

function stubClipboard(onWrite?: (items: unknown[]) => Promise<void>) {
  const writeText = vi.fn(async () => {});
  const write = vi.fn(onWrite ?? (async () => {}));
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { write, writeText },
  });
  return { write, writeText };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('clipboard 表格格式化', () => {
  it('HTML 保留合并单元格与题注，并转义单元格内容', () => {
    const html = tableToHtml(table);
    expect(html).toContain('<table');
    expect(html).toContain('rowspan="2"');
    expect(html).toContain('colspan="2"');
    expect(html).toContain('<caption');
    expect(html).toContain('表 1 职业接触限值');
    expect(html).toContain('&lt;限值&gt;');
    expect(html).not.toContain('<限值>');
  });

  it('单元格子行在富文本里保留为 <br>，纯文本兜底不破坏行列', () => {
    const subrowTable: TableInfo = {
      ...table,
      rows: [[
        { text: '粉尘\n纤维', rowspan: 1, colspan: 1 },
        { text: 'Asbestos dust\nAsbestos fibre', rowspan: 1, colspan: 1 },
      ]],
    };
    const html = tableToHtml(subrowTable);
    expect(html).toContain('粉尘<br>纤维');
    expect(html).toContain('Asbestos dust<br>Asbestos fibre');
    expect(html).not.toContain('粉尘\n纤维');
    expect(tableToPlain(subrowTable)).toBe(
      '表 1 职业接触限值\n粉尘 纤维\tAsbestos dust Asbestos fibre',
    );
  });

  it('纯文本兜底带题注且用制表符分列', () => {
    const plain = tableToPlain(table);
    const lines = plain.split('\n');
    expect(lines[0]).toBe('表 1 职业接触限值');
    expect(lines[1]).toBe('物质\t<限值>');
    expect(lines[2]).toBe('苯\t6\t10');
  });
});

describe('clipboard 写入', () => {
  it('表格同时写入 text/html 与 text/plain，HTML 含合并单元格', async () => {
    vi.stubGlobal('ClipboardItem', FakeClipboardItem);
    vi.stubGlobal('Blob', FakeBlob);
    const { write, writeText } = stubClipboard();
    await copyRichTable(table);
    expect(write).toHaveBeenCalledTimes(1);
    expect(writeText).not.toHaveBeenCalled();
    const call = write.mock.calls[0] as unknown as [FakeClipboardItem[]];
    const item = call[0]?.[0];
    expect(item).toBeDefined();
    const parts = item?.items ?? {};
    expect(Object.keys(parts).sort()).toEqual(['text/html', 'text/plain']);
    expect(await parts['text/html']?.text()).toContain('rowspan="2"');
    expect(await parts['text/plain']?.text()).toContain('苯\t6\t10');
  });

  it('富文本写入失败时降级为纯文本表格', async () => {
    vi.stubGlobal('ClipboardItem', FakeClipboardItem);
    vi.stubGlobal('Blob', FakeBlob);
    const { write, writeText } = stubClipboard(async () => {
      throw new Error('denied');
    });
    await copyRichTable(table);
    expect(write).toHaveBeenCalledTimes(1);
    expect(writeText).toHaveBeenCalledWith(tableToPlain(table));
  });

  it('无 ClipboardItem 时用传统方式复制富文本，仍保留表格结构', async () => {
    vi.stubGlobal('ClipboardItem', undefined);
    const { write } = stubClipboard();
    const exec = vi.fn(() => true);
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: exec,
    });
    let copiedHtml = '';
    const originalCreateElement = document.createElement.bind(document);
    const createSpy = vi
      .spyOn(document, 'createElement')
      .mockImplementation((tag: string, options?: ElementCreationOptions) => {
        const element = originalCreateElement(tag, options);
        if (tag === 'div' && element instanceof HTMLDivElement) {
          Object.defineProperty(element, 'innerHTML', {
            configurable: true,
            get: () => copiedHtml,
            set: (value: string) => {
              copiedHtml = value;
            },
          });
        }
        return element;
      });
    await copyRichTable(table);
    expect(write).not.toHaveBeenCalled();
    expect(exec).toHaveBeenCalledWith('copy');
    expect(copiedHtml).toContain('rowspan="2"');
    expect(copiedHtml).toContain('&lt;限值&gt;');
    createSpy.mockRestore();
  });

  it('正文按纯文本写入', async () => {
    const { writeText } = stubClipboard();
    await copyPlainText('正文内容。\n第二段。');
    expect(writeText).toHaveBeenCalledWith('正文内容。\n第二段。');
  });
});
