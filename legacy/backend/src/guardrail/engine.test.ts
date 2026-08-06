import { ApplyGuardrailCommand, BedrockRuntimeClient } from '@aws-sdk/client-bedrock-runtime';
import { mockClient } from 'aws-sdk-client-mock';
import { beforeEach, describe, expect, it } from 'vitest';
import { GuardrailEngine } from './engine.js';
import { detectEmergency, EMERGENCY_PATTERNS } from './emergency.js';
import testCases from './test-cases.json' with { type: 'json' };
import type { GuardrailTestCase } from './types.js';

const bedrockMock = mockClient(BedrockRuntimeClient);

describe('emergency detection (H04.2)', () => {
  it('detects every configured emergency keyword', () => {
    for (const pattern of EMERGENCY_PATTERNS) {
      for (const keyword of pattern.keywords) {
        const result = detectEmergency(`我${keyword}了`);
        expect(result?.id).toBe(pattern.id);
      }
    }
  });

  it('returns the fixed safety response text, never a model-generated one', () => {
    const result = detectEmergency('胸口很痛，喘不過氣');
    expect(result?.response).toContain('119');
  });

  it('does not misfire on unrelated text', () => {
    expect(detectEmergency('今天天氣很好')).toBeNull();
  });
});

describe('GuardrailEngine.check', () => {
  const engine = () => new GuardrailEngine(new BedrockRuntimeClient({}), 'gr-123', 'DRAFT');

  beforeEach(() => {
    bedrockMock.reset();
  });

  it('short-circuits to a safety override for emergency content, bypassing Guardrails entirely', async () => {
    const result = await engine().check('我胸口很痛', { elderId: 'e1', conversationType: 'general_chat' });
    expect(result.allowed).toBe(true);
    expect(result.safetyOverrideMessage).toContain('119');
    expect(bedrockMock.calls()).toHaveLength(0);
  });

  it('blocks content Guardrails flags as medical (medication_change topic)', async () => {
    bedrockMock.on(ApplyGuardrailCommand).resolves({
      action: 'GUARDRAIL_INTERVENED',
      assessments: [
        {
          topicPolicy: { topics: [{ name: 'medication_change', type: 'DENY', action: 'BLOCKED' }] },
        },
      ],
    });
    const result = await engine().check('這個藥可以直接停藥嗎？', { elderId: 'e1', conversationType: 'general_chat' });
    expect(result.allowed).toBe(false);
    expect(result.action).toBe('block');
    expect(result.blockedCategories).toContain('medication_change');
    expect(result.safetyOverrideMessage).toBe('這個問題建議您諮詢醫師');
  });

  it('passes normal conversation through unchanged', async () => {
    bedrockMock.on(ApplyGuardrailCommand).resolves({ action: 'NONE', assessments: [] });
    const result = await engine().check('今天天氣真好', { elderId: 'e1', conversationType: 'general_chat' });
    expect(result.allowed).toBe(true);
    expect(result.action).toBe('pass');
    expect(result.blockedCategories).toHaveLength(0);
  });

  it('degrades to pass-through (not a hard failure) when no guardrail is configured for this environment', async () => {
    const noGuardrailEngine = new GuardrailEngine(new BedrockRuntimeClient({}), '');
    const result = await noGuardrailEngine.check('隨便說點什麼', { elderId: 'e1', conversationType: 'general_chat' });
    expect(result.allowed).toBe(true);
    expect(bedrockMock.calls()).toHaveLength(0);
  });
});

describe('guardrail test-case set (task 7.2)', () => {
  const cases = testCases as GuardrailTestCase[];

  it('covers medical interception, emergency override, and normal pass-through categories', () => {
    const categories = new Set(cases.map((c) => c.category));
    expect(categories.has('medication_change')).toBe(true);
    expect(categories.has('diagnosis')).toBe(true);
    expect(categories.has('treatment_decision')).toBe(true);
    expect(categories.has('dosage_recommendation')).toBe(true);
    expect(categories.has('emergency_override')).toBe(true);
    expect([...categories].some((c) => c.startsWith('general_chat') || c.startsWith('health_query'))).toBe(true);
  });

  it('every emergency_override case is detected by detectEmergency()', () => {
    for (const testCase of cases.filter((c) => c.category === 'emergency_override')) {
      expect(detectEmergency(testCase.input)).not.toBeNull();
    }
  });
});
