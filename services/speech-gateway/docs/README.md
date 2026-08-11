# Speech Gateway deployment assets

`services/speech-gateway` is the canonical voice boundary. Its application
routes Mandarin and English through Amazon Transcribe/Polly, and routes
Taiwanese Hokkien (`nan-TW`) and Hakka (`hak-TW`) through private SageMaker
endpoints when they have been explicitly configured.

The runtime adapters are:

- `src/speech_gateway/sagemaker_asr.py`
- `src/speech_gateway/sagemaker_tts.py`

This directory documents the low-resource endpoints and the evidence behind
their model choices:

- [`sagemaker-endpoint-contract.md`](./sagemaker-endpoint-contract.md) — exact
  request/response boundary used by the canonical gateway.
- [`model-selection.md`](./model-selection.md) — benchmark evidence, known
  quality limitations and model-license gates.
- [`MODEL_REGISTRY.json`](./MODEL_REGISTRY.json) — model/revision inventory.
- [`hackathon-deployment-guide.md`](./hackathon-deployment-guide.md) —
  fail-closed deployment steps for synthetic data only.
- `../sagemaker/` — ASR and TTS SageMaker BYOC images.

`zh-TW` and `en-US` do not use these BYOC images. `SAGEMAKER_ASR_ENDPOINT` and
`SAGEMAKER_TTS_ENDPOINT` must remain empty until the corresponding private
endpoint passes its license, deployment and synthetic smoke-test gates. An
endpoint responding successfully proves wire compatibility only; it is not a
quality claim.
