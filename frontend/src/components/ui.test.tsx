import { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';

afterEach(cleanup);
import { ConfirmDialog, TextField } from './ui';

function DialogHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        打开确认
      </button>
      {open && (
        <ConfirmDialog
          title="确认删除"
          description="此操作不可撤销"
          confirmLabel="删除"
          onConfirm={() => setOpen(false)}
          onCancel={() => setOpen(false)}
        />
      )}
    </>
  );
}

test('确认对话框支持 Esc 关闭并恢复触发按钮焦点', async () => {
  render(<DialogHarness />);
  const trigger = screen.getByRole('button', { name: '打开确认' });
  trigger.focus();
  fireEvent.click(trigger);
  await screen.findByRole('dialog');
  await waitFor(() => expect(screen.getByRole('button', { name: '取消' })).toHaveFocus());

  fireEvent.keyDown(document, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(trigger).toHaveFocus();
});

test('确认对话框将 Tab 焦点圈定在内部', async () => {
  render(<DialogHarness />);
  fireEvent.click(screen.getByRole('button', { name: '打开确认' }));
  const cancel = await screen.findByRole('button', { name: '取消' });
  const confirm = screen.getByRole('button', { name: '删除' });

  confirm.focus();
  fireEvent.keyDown(document, { key: 'Tab' });
  expect(cancel).toHaveFocus();

  fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
  expect(confirm).toHaveFocus();
});

test('TextField 将错误信息与输入控件关联', () => {
  render(<TextField label="账号" name="login_name" error="请输入账号" />);
  const input = screen.getByRole('textbox');
  expect(input).toHaveAttribute('aria-invalid', 'true');
  expect(input).toHaveAttribute('aria-describedby', 'login_name-error');
  expect(screen.getByText('请输入账号')).toHaveAttribute('id', 'login_name-error');
});
