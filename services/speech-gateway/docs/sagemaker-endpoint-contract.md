# SageMaker endpoint 契約 + 部署步驟

## 契約權威

正式呼叫端是 `src/speech_gateway/sagemaker_asr.py` 與
`src/speech_gateway/sagemaker_tts.py`。BYOC endpoint 必須完全符合以下契約；不得從
Gradio、模型輸出或舊 backend 路徑推導另一份格式。

### ASR：`nan-TW` / `hak-TW`

Canonical Speech Gateway 送出：

```
InvokeEndpointCommand({
  EndpointName: settings.SAGEMAKER_ASR_ENDPOINT,
  ContentType: 'application/octet-stream',
  Body: <原始音訊 bytes，PCM 或 opus，不是包 WAV header 的檔案>,
  CustomAttributes: JSON.stringify({ language, sampleRate }),  // language: 'nan-TW' | 'hak-TW'
})
```

Endpoint 必須回傳（JSON body）：

```json
{ "text": "轉寫結果", "confidence": 0.0 }
```

`confidence` 缺值時 gateway 會當成 `0`（不會報錯，但信心分數全部變 0 會影響上游
guardrail/確認流程判斷，能給真實數字就給）。回應的 `CustomAttributes`（可選）會被
backend 存成 `modelVersion`，沒有就存 `'unknown'`。

**重點：輸入是 raw PCM/opus bytes，不是 WAV 檔案。** PoC 現有的
`core/speech_adapters.py` 是吃 WAV 檔案上傳（`voice_server.py` 的 `/api/asr`），
两者不一樣，這是唯一需要新寫的轉換邏輯（`inference_asr.py` 的 `input_fn`）：
用 `sampleRate`（`CustomAttributes` 給的）把 raw bytes 轉成 float32 numpy 陣列
餵進既有的 ASR pipeline。

### TTS：`nan-TW` / `hak-TW`

Canonical Speech Gateway 送出：

```
InvokeEndpointCommand({
  EndpointName: settings.SAGEMAKER_TTS_ENDPOINT,
  ContentType: 'application/json',
  Body: JSON.stringify({ text, language, speakingSpeed }),
  // language: 'nan-TW' | 'hak-TW'
  // speakingSpeed: 'slow' | 'normal' | 'fast'
})
```

Endpoint 必須回傳：原始音訊 bytes 當 response body，`ContentType` header（沒帶的話
backend 預設當 `audio/wav`）。

### Adapter 失敗行為

未設定 endpoint 時 Speech Gateway 回 `501`；endpoint invocation 或回應格式失敗時回
`502`，且不洩漏模型或 AWS 內部細節。呼叫端必須保留 Core 的 `reply_text` 作為明確的
文字降級，不得改用另一語言的聲音或自行生成替代內容。

## 部署步驟（目前 `infra/` 未管理這兩個 endpoint，仍是受控手動流程）

沿用 PoC repo `SAGEMAKER_SOP_與待辦清單.md` 的既有規劃，這裡只補上跟這次
container 骨架有關的步驟：

1. **建立 Notebook/EC2 環境**：GPU 用 `ml.g5.xlarge`（24GB）或以上，CPU-only 用
   `ml.m5.2xlarge`（32GB）。IAM Role 要有 ECR pull + S3 讀寫權限。
2. **Build + push BYOC image**（見 `../sagemaker/Dockerfile`）：
   ```bash
   aws ecr create-repository --repository-name speech-gateway-nan-hak
   docker build -t speech-gateway-nan-hak services/speech-gateway/sagemaker
   docker tag speech-gateway-nan-hak:latest <account>.dkr.ecr.<region>.amazonaws.com/speech-gateway-nan-hak:latest
   docker push <account>.dkr.ecr.<region>.amazonaws.com/speech-gateway-nan-hak:latest
   ```
   為什麼要 BYOC（自帶容器）而不是 SageMaker script mode：hak 的 TTS
   （VoxHakka）需要獨立 venv（`coqui-tts` 釘 `transformers<5`，跟 ASR 用的主環境
   不相容），單一 `requirements.txt` 沒辦法處理兩組互斥的依賴版本，只能在 image
   裡建兩個 Python 環境（沿用 PoC 既有的 subprocess 呼叫模式，見
   `../sagemaker/Dockerfile` 註解）。
3. **建立 Model / EndpointConfig / Endpoint**：ASR 跟 TTS 各自需要一個
   endpoint（`SAGEMAKER_ASR_ENDPOINT`、`SAGEMAKER_TTS_ENDPOINT` 是兩個獨立環境
   變數），可以用同一個 image、不同的 `SAGEMAKER_PROGRAM` 環境變數切換
   entrypoint（`inference_asr.py` vs `inference_tts.py`），或部署兩個獨立
   endpoint——後者比較簡單，先這樣做。
4. **把 endpoint 名稱填進 Speech Gateway 環境變數**：
   `SAGEMAKER_ASR_ENDPOINT`／`SAGEMAKER_TTS_ENDPOINT`。執行角色只授予這兩個私有
   endpoint 所需的 `sagemaker:InvokeEndpoint`。
5. 部署完先用小樣本人工測試 ASR/TTS 各幾筆，確認契約真的對得上（尤其
   `CustomAttributes` 解析、raw PCM bytes 轉換這幾個新寫的邏輯），再讓 backend
   實際打。

任何 AWS 建立、push 或 invoke 都只能在具備核准短效憑證的環境執行。本機沒有有效
憑證時，只進行靜態、單元與容器建置驗證，不得把 endpoint 標記為已部署。
