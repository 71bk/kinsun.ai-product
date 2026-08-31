"""Speech gateway: the Transcribe/Polly boundary for the canonical voice path.

Scope is deliberately narrow. This service converts audio to text and text to
audio. It does not store transcripts, evaluate consent, extract events or decide
anything about an elder's care — those belong to Core, which is the only place
allowed to hold formal state.

Consequence worth stating plainly: because nothing here is persisted, a caller
must still go through Core's consent and voice-session gates before acting on a
transcript. This service being reachable is not authorization to record someone.
"""

from __future__ import annotations

import base64
import binascii
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from speech_gateway.asr import MODEL_VERSION, transcribe_pcm
from speech_gateway.azure_tts import AzureSpeechTtsProvider
from speech_gateway.core_voice_gate import (
    CoreGateRejectedError,
    CoreGateUnavailableError,
    CoreVoiceGateClient,
)
from speech_gateway.deepgram_asr import DeepgramNova3AsrProvider
from speech_gateway.models import (
    SynthesizeRequest,
    SynthesizeResponse,
    TranscribeRequest,
    TranscribeResponse,
)
from speech_gateway.provider_adapters import (
    AwsPollyTtsProvider,
    AwsTranscribeAsrProvider,
    SageMakerAsrProvider,
    SageMakerTtsProvider,
)
from speech_gateway.provider_contracts import (
    AsrProviderRequest,
    ProviderErrorCategory,
    SpeechProviderError,
    TtsProviderRequest,
)
from speech_gateway.provider_router import SpeechProviderRouter
from speech_gateway.sagemaker_asr import transcribe_via_sagemaker
from speech_gateway.sagemaker_tts import synthesize_via_sagemaker
from speech_gateway.service_identity import ServiceCredentialSigner
from speech_gateway.settings import get_settings
from speech_gateway.tts import synthesize

logger = logging.getLogger("speech_gateway")

# Raw audio and transcripts are Restricted Data, so failures are logged by
# category only. No audio bytes and no recognised text reach the log.
MAX_AUDIO_BYTES = 5 * 1024 * 1024


_CORE_LANGUAGE_ROUTES = {
    "zh-TW": "ZH_TW",
    "en-US": "EN_US",
    "nan-TW": "NAN_TW",
    "hak-TW": "HAK_TW",
}

_AFFIRMATIVE_MEMORY_ANSWERS = frozenset({"是", "好", "可以", "記住", "yes"})
_REJECT_MEMORY_ANSWERS = frozenset({"不是", "不要", "不用", "no"})
_DEFER_MEMORY_ANSWERS = frozenset({"稍後", "晚點", "下次", "later"})


def _memory_response_intent(text: str) -> str:
    normalized = "".join(text.casefold().strip().split()).rstrip("。！？!?")
    if normalized in _AFFIRMATIVE_MEMORY_ANSWERS:
        return "AFFIRM"
    if normalized in _REJECT_MEMORY_ANSWERS:
        return "REJECT"
    if normalized in _DEFER_MEMORY_ANSWERS:
        return "DEFER"
    return "UNCERTAIN"


def create_app(
    core_client: CoreVoiceGateClient | None = None,
    provider_router: SpeechProviderRouter | None = None,
) -> FastAPI:
    settings = get_settings()
    providers = provider_router or _build_provider_router(settings)
    core = core_client or CoreVoiceGateClient(
        base_url=settings.CORE_API_BASE_URL,
        timeout_seconds=settings.CORE_API_TIMEOUT_SECONDS,
        service_token=settings.CORE_API_SERVICE_TOKEN,
        service_signer=(
            ServiceCredentialSigner(
                secret=settings.CORE_API_SERVICE_IDENTITY_HMAC_SECRET,
                issuer=settings.CORE_API_SERVICE_IDENTITY_ISSUER,
                ttl_seconds=settings.CORE_API_SERVICE_IDENTITY_TTL_SECONDS,
            )
            if settings.CORE_API_SERVICE_IDENTITY_ENABLED
            else None
        ),
    )
    app = FastAPI(title="kinsun-speech-gateway", version="0.1.0")

    @app.exception_handler(RequestValidationError)
    async def safe_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Reject malformed audio/tickets without echoing Restricted Data."""
        logger.warning(
            "request validation failed",
            extra={"path": request.url.path, "error_count": len(exc.errors())},
        )
        return JSONResponse(status_code=422, content={"detail": "request validation failed"})

    # Local development only: the browser page used for manual voice checks is
    # served from a different port. A deployed gateway must be reached through
    # the BFF, not directly from a browser.
    if settings.APP_ENV == "local":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
            allow_methods=["POST"],
            allow_headers=["content-type"],
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "speech-gateway", "version": "0.1.0"}

    @app.post("/api/v1/speech/transcriptions", response_model=TranscribeResponse)
    async def create_transcription(payload: TranscribeRequest) -> TranscribeResponse:
        try:
            audio = base64.b64decode(payload.audio_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=422, detail="audio_base64 is not valid base64") from exc

        if not audio:
            raise HTTPException(status_code=422, detail="audio payload is empty")
        if len(audio) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="audio payload is too large")

        try:
            await core.consume_ticket(
                session_id=payload.session_id,
                voice_ticket=payload.voice_ticket,
            )
        except CoreGateRejectedError as exc:
            raise HTTPException(status_code=403, detail="voice session unavailable") from exc
        except CoreGateUnavailableError as exc:
            raise HTTPException(status_code=503, detail="voice safety gate unavailable") from exc

        try:
            result = await providers.transcribe(
                AsrProviderRequest(
                    audio=audio,
                    language=payload.language,
                    sample_rate=payload.sample_rate,
                )
            )
        except SpeechProviderError as exc:
            logger.warning(
                "ASR provider failed",
                extra={
                    "speech_provider": exc.provider_key,
                    "provider_error_category": exc.category.value,
                    "language": payload.language,
                },
            )
            await _fail_consumed_session(core, payload.session_id)
            if exc.category in {
                ProviderErrorCategory.MISCONFIGURED,
                ProviderErrorCategory.UNSUPPORTED_LANGUAGE,
            }:
                raise HTTPException(
                    status_code=501,
                    detail="this language is not available in this deployment",
                ) from exc
            raise HTTPException(
                status_code=502,
                detail="speech recognition unavailable",
            ) from exc

        if not result.text.strip():
            await _fail_consumed_session(core, payload.session_id)
            raise HTTPException(status_code=422, detail="speech recognition returned no text")

        logger.info(
            "ASR provider completed",
            extra={
                "speech_provider": result.metadata.provider_key,
                "provider_model_version": result.metadata.model_version,
                "language": payload.language,
            },
        )

        try:
            decision = await core.submit_asr_result(
                session_id=payload.session_id,
                language_route=_CORE_LANGUAGE_ROUTES[payload.language],
                model_version=result.metadata.model_version,
                confidence=result.confidence,
                transcript=result.text,
            )
        except CoreGateRejectedError as exc:
            await _fail_consumed_session(core, payload.session_id)
            raise HTTPException(status_code=403, detail="voice session unavailable") from exc
        except CoreGateUnavailableError as exc:
            await _fail_consumed_session(core, payload.session_id)
            raise HTTPException(status_code=503, detail="voice safety gate unavailable") from exc

        memory_decision = None
        confirmation = payload.memory_confirmation
        if confirmation is not None and decision.decision == "CAN_SEND_TO_AGENT":
            response_intent = _memory_response_intent(result.text)
            try:
                memory_result = await core.decide_memory_by_voice(
                    elder_id=confirmation.elder_id,
                    memory_id=confirmation.memory_id,
                    session_id=payload.session_id,
                    confirmation_method=confirmation.confirmation_method,
                    expected_candidate_version=confirmation.expected_candidate_version,
                    consent_version=confirmation.consent_version,
                    confirmation_question_digest=(confirmation.confirmation_question_digest),
                    response_intent=response_intent,
                    witness_actor_id=confirmation.witness_actor_id,
                    witness_evidence_reference=(confirmation.witness_evidence_reference),
                )
            except CoreGateRejectedError as exc:
                raise HTTPException(
                    status_code=403,
                    detail="memory confirmation unavailable",
                ) from exc
            except CoreGateUnavailableError as exc:
                raise HTTPException(
                    status_code=503,
                    detail="memory confirmation unavailable",
                ) from exc
            memory_decision = memory_result.status

        return TranscribeResponse(
            session_id=payload.session_id,
            text=result.text,
            language=payload.language,
            model_version=result.metadata.model_version,
            gate_decision=decision.decision,
            confirmation_required=decision.confirmation_required,
            gate_expires_at=decision.expires_at,
            memory_decision=memory_decision,
        )

    @app.post("/api/v1/speech/syntheses", response_model=SynthesizeResponse)
    async def create_synthesis(payload: SynthesizeRequest) -> SynthesizeResponse:
        try:
            result = await providers.synthesize(
                TtsProviderRequest(
                    text=payload.text,
                    language=payload.language,
                    speaking_speed=payload.speaking_speed,
                )
            )
        except SpeechProviderError as exc:
            logger.warning(
                "TTS provider failed",
                extra={
                    "speech_provider": exc.provider_key,
                    "provider_error_category": exc.category.value,
                    "language": payload.language,
                },
            )
            if exc.category in {
                ProviderErrorCategory.MISCONFIGURED,
                ProviderErrorCategory.UNSUPPORTED_LANGUAGE,
            }:
                raise HTTPException(
                    status_code=501,
                    detail="this language is not available in this deployment",
                ) from exc
            raise HTTPException(status_code=502, detail="speech synthesis unavailable") from exc

        logger.info(
            "TTS provider completed",
            extra={
                "speech_provider": result.metadata.provider_key,
                "provider_model_version": result.metadata.model_version,
                "language": payload.language,
            },
        )

        return SynthesizeResponse(
            audio_base64=base64.b64encode(result.audio).decode("ascii"),
            content_type=result.content_type,
            voice_id=result.voice_id,
        )

    return app


def _build_provider_router(settings) -> SpeechProviderRouter:  # noqa: ANN001
    """Build the closed runtime registry from server-owned configuration."""
    return SpeechProviderRouter(
        asr_providers=(
            AwsTranscribeAsrProvider(
                region=settings.AWS_REGION,
                transcribe=_call_transcribe_pcm,
                model_version=MODEL_VERSION,
            ),
            SageMakerAsrProvider(
                region=settings.AWS_REGION,
                endpoint_name=settings.SAGEMAKER_ASR_ENDPOINT,
                transcribe=_call_transcribe_via_sagemaker,
            ),
            DeepgramNova3AsrProvider(
                api_key=settings.DEEPGRAM_API_KEY,
                base_url=settings.DEEPGRAM_API_BASE_URL,
                timeout_seconds=settings.ASR_PROVIDER_TIMEOUT_SECONDS,
            ),
        ),
        tts_providers=(
            AzureSpeechTtsProvider(
                subscription_key=settings.AZURE_SPEECH_KEY,
                region=settings.AZURE_SPEECH_REGION,
                voice_zh_tw=settings.AZURE_SPEECH_TTS_VOICE_ZH_TW,
                voice_en_us=settings.AZURE_SPEECH_TTS_VOICE_EN_US,
                timeout_seconds=settings.TTS_PROVIDER_TIMEOUT_SECONDS,
            ),
            AwsPollyTtsProvider(
                region=settings.AWS_REGION,
                synthesize=_call_synthesize,
            ),
            SageMakerTtsProvider(
                region=settings.AWS_REGION,
                endpoint_name=settings.SAGEMAKER_TTS_ENDPOINT,
                synthesize=_call_synthesize_via_sagemaker,
            ),
        ),
        asr_routes=settings.asr_provider_routes(),
        tts_routes=settings.tts_provider_routes(),
        asr_timeout_seconds=settings.ASR_PROVIDER_TIMEOUT_SECONDS,
        tts_timeout_seconds=settings.TTS_PROVIDER_TIMEOUT_SECONDS,
    )


async def _call_transcribe_pcm(audio, language, sample_rate, region):  # noqa: ANN001, ANN202
    return await transcribe_pcm(audio, language, sample_rate, region)


async def _call_transcribe_via_sagemaker(  # noqa: ANN001, ANN202
    audio,
    language,
    sample_rate,
    region,
    endpoint_name,
):
    return await transcribe_via_sagemaker(
        audio,
        language,
        sample_rate,
        region,
        endpoint_name,
    )


async def _call_synthesize(text, language, speaking_speed, region):  # noqa: ANN001, ANN202
    return await synthesize(text, language, speaking_speed, region)


async def _call_synthesize_via_sagemaker(  # noqa: ANN001, ANN202
    text,
    language,
    speaking_speed,
    region,
    endpoint_name,
):
    return await synthesize_via_sagemaker(
        text,
        language,
        speaking_speed,
        region,
        endpoint_name,
    )


async def _fail_consumed_session(
    core: CoreVoiceGateClient,
    session_id,
) -> None:
    try:
        await core.fail_session(session_id=session_id)
    except (CoreGateRejectedError, CoreGateUnavailableError):
        logger.warning("could not mark failed voice session")


app = create_app()
