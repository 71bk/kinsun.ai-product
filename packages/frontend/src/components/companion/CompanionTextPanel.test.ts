// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ create: vi.fn(), run: vi.fn(), remove: vi.fn() }));
vi.mock('@/lib/api/companion', () => ({
  createTextSession: mocks.create,
  runCompanionTurn: mocks.run,
}));
vi.mock('@/lib/api/memories', () => ({ deleteMemoryAsElder: mocks.remove }));
vi.mock('@/components/voice/CompanionCharacter', () => ({
  CompanionCharacter: ({ message }: { message: string }) => createElement('p', null, message),
}));
import { CompanionTextPanel } from './CompanionTextPanel';
const config = { apiBaseUrl: '/backend/core' };
const receipt = { memory_id: 'synthetic-memory', version: 2, content: '我每天早餐喝豆漿。' };
const reply = { reply_text: '謝謝您分享。', safety_decision: 'ALLOW', memory_updates: [receipt] };
beforeEach(() => {
  mocks.create.mockReset().mockResolvedValue({ session_id: 'new-session' });
  mocks.run.mockReset().mockResolvedValue(reply);
  mocks.remove.mockReset().mockResolvedValue(undefined);
});
afterEach(() => {
  cleanup();
});
async function send(text = '我每天早餐喝豆漿') {
  fireEvent.change(screen.getByRole('textbox', { name: '想和小暖說什麼？' }), {
    target: { value: text },
  });
  fireEvent.click(screen.getByRole('button', { name: '送出文字' }));
  await screen.findByText('謝謝您分享。');
}
it('shows only Core receipts and undoes the exact saved version', async () => {
  render(createElement(CompanionTextPanel, { apiConfig: config, elderId: 'elder-a' }));
  await send();
  expect(screen.getByText('已記住')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '撤銷這筆記憶' }));
  await screen.findByText('已撤銷這筆記憶，新對話不會再使用它。');
  expect(mocks.remove).toHaveBeenCalledWith(config, 'elder-a', {
    memoryId: 'synthetic-memory',
    version: 2,
  });
  expect(screen.queryByText('已記住')).toBeNull();
});
it('opens a new session and sends only the new question', async () => {
  mocks.create
    .mockResolvedValueOnce({ session_id: 'first' })
    .mockResolvedValueOnce({ session_id: 'second' });
  render(createElement(CompanionTextPanel, { apiConfig: config, elderId: 'elder-a' }));
  await send();
  fireEvent.click(screen.getByRole('button', { name: '開始新對話' }));
  expect(screen.queryByText('已記住')).toBeNull();
  await send('我早餐習慣喝什麼？');
  expect(mocks.create).toHaveBeenCalledTimes(2);
  expect(mocks.run).toHaveBeenLastCalledWith(config, 'second', '我早餐習慣喝什麼？');
});
it('does not claim a save without a receipt', async () => {
  mocks.run.mockResolvedValue({ ...reply, memory_updates: [] });
  render(createElement(CompanionTextPanel, { apiConfig: config, elderId: 'elder-a' }));
  await send();
  expect(screen.queryByRole('button', { name: '撤銷這筆記憶' })).toBeNull();
});
it('keeps the receipt if undo has an uncertain result', async () => {
  mocks.remove.mockRejectedValue(new Error('Network unavailable'));
  render(createElement(CompanionTextPanel, { apiConfig: config, elderId: 'elder-a' }));
  await send();
  fireEvent.click(screen.getByRole('button', { name: '撤銷這筆記憶' }));
  await screen.findByRole('alert');
  expect(screen.getByText('已記住')).toBeTruthy();
  expect(screen.queryByText('已撤銷這筆記憶，新對話不會再使用它。')).toBeNull();
});
it('ignores a late save response after the elder changes', async () => {
  let resolve: (value: typeof reply) => void = () => undefined;
  mocks.run.mockReturnValue(
    new Promise<typeof reply>((done) => {
      resolve = done;
    }),
  );
  const view = render(createElement(CompanionTextPanel, { apiConfig: config, elderId: 'elder-a' }));
  fireEvent.change(screen.getByRole('textbox', { name: '想和小暖說什麼？' }), {
    target: { value: '我喜歡聽老歌' },
  });
  fireEvent.click(screen.getByRole('button', { name: '送出文字' }));
  await waitFor(() => expect(mocks.run).toHaveBeenCalled());
  view.rerender(createElement(CompanionTextPanel, { apiConfig: config, elderId: 'elder-b' }));
  resolve(reply);
  await waitFor(() => expect(screen.getByRole('button', { name: '送出文字' })).toBeTruthy());
  expect(screen.queryByText('已記住')).toBeNull();
});
