import { PollyClient, SynthesizeSpeechCommand, VoiceId } from '@aws-sdk/client-polly';
import { InvokeEndpointCommand, SageMakerRuntimeClient } from '@aws-sdk/client-sagemaker-runtime';
import type { ConcreteLanguage } from './types.js';

export interface TtsAdapterResult {
  audio: Uint8Array;
  contentType: string;
}

export interface TtsAdapter {
  synthesize(text: string, language: ConcreteLanguage, speakingSpeed: 'slow' | 'normal' | 'fast'): Promise<TtsAdapterResult>;
}

const POLLY_VOICE_BY_LANGUAGE: Record<'zh-TW' | 'en-US', VoiceId> = {
  'zh-TW': VoiceId.Zhiyu, // Amazon Polly Mandarin neural voice
  'en-US': VoiceId.Joanna,
};

const SSML_RATE: Record<'slow' | 'normal' | 'fast', string> = { slow: '80%', normal: '100%', fast: '120%' };

function toSsml(text: string, speakingSpeed: 'slow' | 'normal' | 'fast'): string {
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return `<speak><prosody rate="${SSML_RATE[speakingSpeed]}">${escaped}</prosody></speak>`;
}

/** Amazon Polly — Mandarin and English TTS (A03.2). */
export class PollyAdapter implements TtsAdapter {
  constructor(private readonly client: PollyClient = new PollyClient({})) {}

  async synthesize(
    text: string,
    language: 'zh-TW' | 'en-US',
    speakingSpeed: 'slow' | 'normal' | 'fast',
  ): Promise<TtsAdapterResult> {
    const response = await this.client.send(
      new SynthesizeSpeechCommand({
        Text: toSsml(text, speakingSpeed),
        TextType: 'ssml',
        OutputFormat: 'mp3',
        VoiceId: POLLY_VOICE_BY_LANGUAGE[language],
        Engine: 'neural',
      }),
    );
    if (!response.AudioStream) {
      throw new Error('Polly returned no audio stream');
    }
    const audio = await response.AudioStream.transformToByteArray();
    return { audio, contentType: response.ContentType ?? 'audio/mpeg' };
  }
}

/** Self-hosted SageMaker endpoint — Hokkien and Hakka TTS (A03.3). */
export class SageMakerTtsAdapter implements TtsAdapter {
  constructor(
    private readonly endpointName: string = process.env.TTS_SAGEMAKER_ENDPOINT ?? '',
    private readonly client: SageMakerRuntimeClient = new SageMakerRuntimeClient({}),
  ) {}

  async synthesize(
    text: string,
    language: 'nan-TW' | 'hak-TW',
    speakingSpeed: 'slow' | 'normal' | 'fast',
  ): Promise<TtsAdapterResult> {
    if (!this.endpointName) {
      throw new Error('TTS_SAGEMAKER_ENDPOINT is not configured');
    }
    const response = await this.client.send(
      new InvokeEndpointCommand({
        EndpointName: this.endpointName,
        ContentType: 'application/json',
        Body: JSON.stringify({ text, language, speakingSpeed }),
      }),
    );
    if (!response.Body) {
      throw new Error('SageMaker TTS endpoint returned no body');
    }
    return { audio: response.Body, contentType: response.ContentType ?? 'audio/wav' };
  }
}
