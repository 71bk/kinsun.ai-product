import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import type { MemoryView } from '@/lib/api/memories';
import { MemoryCard } from '../memory/MemoryCard';

function source(relativeUrl: string): string {
  return readFileSync(fileURLToPath(new URL(relativeUrl, import.meta.url)), 'utf8');
}

const candidate: MemoryView = {
  memoryId: 'synthetic-memory',
  elderId: 'synthetic-elder',
  memoryType: 'PREFERENCE',
  content: '喜歡在下午聽音樂',
  status: 'CANDIDATE',
  sourceEventIds: ['opaque-reference-must-not-render'],
  confirmedBy: 'internal-actor-must-not-render',
  confirmedAt: null,
  version: 3,
  consentVersion: 2,
  createdAt: '2026-08-13T00:00:00Z',
  updatedAt: '2026-08-13T00:00:00Z',
};

describe('Elder Surface safety semantics', () => {
  it('offers only routes backed by the current product and API boundary', () => {
    const shell = source('./ElderShell.tsx');

    expect(shell).toContain("href: '/elder/memories'");
    expect(shell).toContain("href: '/consent'");
    expect(shell).toContain("href: '/elder/family-access'");
    expect(shell).not.toMatch(/href:\s*['"]\/(health|schedule|emergency|sos)/i);
    expect(shell).not.toMatch(/ambulance|救護車/i);
  });

  it('keeps candidate memories visibly unconfirmed and hides opaque references', () => {
    const markup = renderToStaticMarkup(
      createElement(LocaleProvider, {
        initialLocale: 'zh-Hant',
        children: createElement(MemoryCard, {
          memory: candidate,
          mode: 'candidate',
          onCommand: async () => undefined,
        }),
      }),
    );

    expect(markup).toContain('小暖想記住');
    expect(markup).toContain('等待您確認');
    expect(markup).toContain('是，請記住');
    expect(markup).toContain('不是這樣');
    expect(markup).not.toContain('opaque-reference-must-not-render');
    expect(markup).not.toContain('internal-actor-must-not-render');
  });

  it('states the voice, consent and family-sharing product boundaries explicitly', () => {
    const voice = source('../voice/VoiceHomeClient.tsx');
    const consent = source('../../app/consent/page.tsx');
    const family = source('../../app/elder/family-access/page.tsx');

    expect(voice).toMatch(/不會診斷、改藥、停藥/);
    expect(voice).toMatch(/緊急服務/);
    expect(consent).toMatch(/健康風險|情緒風險/);
    expect(family).toMatch(/不會讓家屬看到逐字稿、記憶、草稿或照護內部資料/);
    expect(family).toMatch(/只分享正式報表/);
  });
});

describe('Elder Surface styling boundary', () => {
  it.each([
    'ElderShell.module.css',
    '../memory/MemoryCard.module.css',
    '../consent/ConsentPurposeControl.module.css',
    '../consent/ConsentSummary.module.css',
    '../voice/VoiceHomeClient.module.css',
    '../voice/VoiceInteractionPanel.module.css',
    '../voice/LanguageSelect.module.css',
    '../voice/MicPermissionGuide.module.css',
    '../InputModeToggle.module.css',
    '../companion/CompanionTextPanel.module.css',
    '../../app/consent/ConsentPage.module.css',
    '../../app/elder/memories/ElderMemoriesPage.module.css',
    '../../app/elder/family-access/FamilyAccessPage.module.css',
    '../../app/elder/start/ElderAuthView.module.css',
  ])('%s uses tokens instead of raw hex colours', (relativePath) => {
    const css = source(relativePath);
    expect(css).not.toMatch(/#(?:[0-9a-fA-F]{3,4}){1,2}\b/);
    expect(css).not.toMatch(/@tailwind|theme\(/i);
  });

  it('stacks the interaction workspace and memory actions on narrow screens', () => {
    const interactionCss = source('../voice/VoiceInteractionPanel.module.css');
    const memoryCss = source('../memory/MemoryCard.module.css');

    expect(interactionCss).toMatch(/@media\s*\(min-width:\s*75rem\)/);
    expect(memoryCss).toMatch(/@media\s*\(max-width:\s*48rem\)/);
    expect(memoryCss).not.toMatch(/overflow-x:\s*(auto|scroll)/);
  });
});
