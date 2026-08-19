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
| ASR | `aws-sagemaker` | Private SageMaker endpoint | `nan-TW`, `hak-TW` |
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
TTS_PROVIDER_ZH_TW=aws-polly
TTS_PROVIDER_EN_US=aws-polly
TTS_PROVIDER_NAN_TW=aws-sagemaker
TTS_PROVIDER_HAK_TW=aws-sagemaker
ASR_PROVIDER_TIMEOUT_SECONDS=30
TTS_PROVIDER_TIMEOUT_SECONDS=30
```

`SAGEMAKER_ASR_ENDPOINT` and `SAGEMAKER_TTS_ENDPOINT` remain separate required
configuration for the private adapters. Route changes take effect after the
service restarts.

For a local Docker smoke test, pass the same server-owned variables to the
container; do not expose them as `NEXT_PUBLIC_*` values:

```powershell
docker build -t kinsun-speech-gateway services/speech-gateway
docker run --rm -p 8002:8002 `
  -e ASR_PROVIDER_ZH_TW=aws-transcribe `
  -e ASR_PROVIDER_EN_US=aws-transcribe `
  -e ASR_PROVIDER_NAN_TW=aws-sagemaker `
  -e ASR_PROVIDER_HAK_TW=aws-sagemaker `
  -e TTS_PROVIDER_ZH_TW=aws-polly `
  -e TTS_PROVIDER_EN_US=aws-polly `
  -e TTS_PROVIDER_NAN_TW=aws-sagemaker `
  -e TTS_PROVIDER_HAK_TW=aws-sagemaker `
  kinsun-speech-gateway
```

AWS credentials, the Core service credential, and private endpoint names must
be supplied through the deployment's secret/configuration mechanism. Do not put
them in an image, browser bundle, command history, or committed file.

## Validation and failure behavior

- Unknown provider keys, incomplete routes, unsupported provider/language
  combinations, and invalid timeouts stop application construction.
- Missing private endpoint configuration fails on first use with a bounded
  `misconfigured` category and HTTP 501.
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
