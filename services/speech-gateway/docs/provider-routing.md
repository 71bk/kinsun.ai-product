# Server-owned speech provider routing

Speech Gateway selects ASR and TTS providers from environment configuration.
The public request contract contains no provider field, and Pydantic rejects
extra fields, so a browser cannot choose where audio or transcript content is
sent.

## Runtime registry

The runtime process registers only these adapters:

| Capability | Provider key | Current implementation | Languages |
| --- | --- | --- | --- |
| ASR | `aws-transcribe` | Amazon Transcribe Streaming | `zh-TW`, `en-US` |
| ASR | `deepgram-nova-3` | Deepgram pre-recorded Nova-3 API | `zh-TW`, `en-US` |
| ASR | `aws-sagemaker` | Private SageMaker endpoint | `nan-TW`, `hak-TW` |
| TTS | `azure-speech-tts` | Azure AI Speech REST synthesis | `zh-TW`, `en-US` |
| TTS | `aws-polly` | Amazon Polly neural voices | `zh-TW`, `en-US` |
| TTS | `aws-sagemaker` | Private SageMaker endpoint | `nan-TW`, `hak-TW` |

Deterministic adapters exist only inside `tests/test_provider_router.py`. The
production registry cannot select them.

## Configuration

Each supported language has an independent server-side route:

```dotenv
ASR_PROVIDER_ZH_TW=aws-transcribe
ASR_PROVIDER_EN_US=aws-transcribe
ASR_PROVIDER_NAN_TW=aws-sagemaker
ASR_PROVIDER_HAK_TW=aws-sagemaker
TTS_PROVIDER_ZH_TW=azure-speech-tts
TTS_PROVIDER_EN_US=azure-speech-tts
TTS_PROVIDER_NAN_TW=aws-sagemaker
TTS_PROVIDER_HAK_TW=aws-sagemaker
ASR_PROVIDER_TIMEOUT_SECONDS=30
TTS_PROVIDER_TIMEOUT_SECONDS=30
TTS_MAX_CONCURRENCY=4
TTS_CONCURRENCY_RETRY_AFTER_SECONDS=1
TTS_CLIENT_IP_HASH_SECRET=<deployment-secret>
DEEPGRAM_API_KEY=
DEEPGRAM_API_BASE_URL=https://api.deepgram.com
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=
AZURE_SPEECH_TTS_VOICE_ZH_TW=zh-TW-HsiaoChenNeural
AZURE_SPEECH_TTS_VOICE_EN_US=en-US-JennyNeural
```

`SAGEMAKER_ASR_ENDPOINT` and `SAGEMAKER_TTS_ENDPOINT` remain separate required
configuration for the private adapters. Route changes take effect after the
service restarts.

Every TTS request must carry a short-lived bearer capability issued with the
completed Core companion turn. The capability binds the session, Agent run,
tenant, actor, exact UTF-8 text digest, character count, language, and expiry.
Speech Gateway consumes it exactly once through Core using the request-bound
Speech service identity before any provider call. Core serializes quota checks
in PostgreSQL for client-address pseudonym, actor, and tenant; Gateway also
rejects work above `TTS_MAX_CONCURRENCY` immediately. Both quota and capacity
responses are HTTP 429 with a bounded `Retry-After`, and provider failures always
release the local concurrency slot. `TTS_CLIENT_IP_HASH_SECRET` is required
outside local development and must not reuse the service-identity secret.

Deepgram is opt-in. To use Nova-3 for Traditional Mandarin and US English while
preserving the low-resource routes, set:

```dotenv
ASR_PROVIDER_ZH_TW=deepgram-nova-3
ASR_PROVIDER_EN_US=deepgram-nova-3
ASR_PROVIDER_NAN_TW=aws-sagemaker
ASR_PROVIDER_HAK_TW=aws-sagemaker
DEEPGRAM_API_KEY=<deployment-secret>
```

The adapter always sends raw mono linear16 PCM with an explicit sample rate,
`model=nova-3`, a fixed `zh-TW` or `en-US` language, `channels=1`, and
`mip_opt_out=true`. Model selection, endpoint, privacy policy, and credentials
are not accepted from the public API. Deepgram is not registered for `nan-TW`
or `hak-TW`; selecting it for either language stops application construction.
The normalized confidence is the minimum valid word confidence when word data
is present, keeping the downstream Core gate conservative.

Azure Speech is the default TTS route for Traditional Mandarin and US English.
The adapter derives the REST endpoint from the server-owned region, XML-escapes
input before placing it in SSML, and fixes output to
`audio-24khz-48kbitrate-mono-mp3`. The default voices are
`zh-TW-HsiaoChenNeural` and `en-US-JennyNeural`; deployments may change them
only through server configuration. `slow`, `normal`, and `fast` map to bounded
SSML prosody rates of `-20%`, `0%`, and `+20%`. Azure is not registered for
`nan-TW` or `hak-TW`.

For a local Docker smoke test, pass the same server-owned variables to the
container; do not expose them as `NEXT_PUBLIC_*` values:

```powershell
docker build -t kinsun-speech-gateway services/speech-gateway
docker run --rm -p 8002:8002 `
  -e ASR_PROVIDER_ZH_TW=aws-transcribe `
  -e ASR_PROVIDER_EN_US=aws-transcribe `
  -e ASR_PROVIDER_NAN_TW=aws-sagemaker `
  -e ASR_PROVIDER_HAK_TW=aws-sagemaker `
  -e TTS_PROVIDER_ZH_TW=azure-speech-tts `
  -e TTS_PROVIDER_EN_US=azure-speech-tts `
  -e TTS_PROVIDER_NAN_TW=aws-sagemaker `
  -e TTS_PROVIDER_HAK_TW=aws-sagemaker `
  kinsun-speech-gateway
```

AWS credentials, the Core service credential, and private endpoint names must
be supplied through the deployment's secret/configuration mechanism. The same
applies to `DEEPGRAM_API_KEY` and `AZURE_SPEECH_KEY`. Do not put credentials in
an image, browser bundle, command history, or committed file.

## Validation and failure behavior

- Unknown provider keys, incomplete routes, unsupported provider/language
  combinations, and invalid timeouts stop application construction.
- Missing private endpoint, selected Deepgram credential, or selected Azure
  key/region configuration fails on first use with a bounded `misconfigured`
  category and HTTP 501.
- Timeouts, upstream failures, and invalid provider responses fail with bounded
  categories and HTTP 502.
- The router calls exactly one configured provider. It never silently falls
  back or sends content to another provider.
- Audit logs contain only normalized provider key, model identifier, language,
  and bounded error category. Audio, transcript text, credentials, and upstream
  error messages are excluded.

Adding another provider requires a new adapter implementing the protocols in
`provider_contracts.py`, explicit runtime registration, server-side route
configuration, tests, and a separate provider approval decision.
