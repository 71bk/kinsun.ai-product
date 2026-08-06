import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import type { ConcreteLanguage } from './types.js';
import { routeEndpoint, SUPPORTED_LANGUAGES_BY_ENDPOINT } from './routing.js';

const concreteLanguageArb = fc.constantFrom<ConcreteLanguage>('zh-TW', 'en-US', 'nan-TW', 'hak-TW');

/**
 * Feature: elderly-care-ai-companion, Property 1: ASR 語言路由正確性.
 * For any language preference/detected-language combination, Mandarin and
 * English must route to Transcribe, Hokkien and Hakka must route to
 * SageMaker, and no language is ever routed to an endpoint that doesn't
 * support it.
 */
describe('Property 1: ASR language routing correctness', () => {
  it('routes every concrete language to an endpoint that declares support for it', () => {
    fc.assert(
      fc.property(concreteLanguageArb, (language) => {
        const endpoint = routeEndpoint(language);
        expect(SUPPORTED_LANGUAGES_BY_ENDPOINT[endpoint]).toContain(language);
      }),
      { numRuns: 200 },
    );
  });

  it('never routes Mandarin/English to SageMaker or Hokkien/Hakka to Transcribe', () => {
    fc.assert(
      fc.property(concreteLanguageArb, (language) => {
        const endpoint = routeEndpoint(language);
        if (language === 'zh-TW' || language === 'en-US') {
          expect(endpoint).toBe('transcribe');
        } else {
          expect(endpoint).toBe('sagemaker');
        }
      }),
      { numRuns: 200 },
    );
  });

  it('routing is a pure deterministic function (same input -> same output)', () => {
    fc.assert(
      fc.property(concreteLanguageArb, (language) => {
        expect(routeEndpoint(language)).toBe(routeEndpoint(language));
      }),
      { numRuns: 50 },
    );
  });
});
