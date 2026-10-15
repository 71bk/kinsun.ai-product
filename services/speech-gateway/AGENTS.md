# AGENTS.md — speech-gateway

本檔補充根目錄 [`AGENTS.md`](../../AGENTS.md)，只涵蓋 `services/speech-gateway/`；根目錄規則一律適用，
衝突時以根目錄為準。

- Canonical voice flow：Browser JSON audio upload → Core Voice Ticket → Gateway consume → Core server-side
  ASR Gate。低信心結果必須要求確認，前端不得自行 threshold，不可直接成為 verified event 或 memory。
- 對 Core 的私有呼叫使用 `src/speech_gateway/service_identity.py` 簽出的 request-bound 短效憑證（規則見
  [core-api AGENTS](../core-api/AGENTS.md)）。secret 少於 32 bytes 或 TTL 不在 1–60 s 會在啟動時失敗；
  secret 必須與 Core 相等，且不得重用 Core→Agent Runtime 或任何 Voice／OAuth／provider secret。
- `/internal/.../voice-confirmation` 與 voice-session endpoint 於認證後從已存的 ConversationSession 解析
  tenant／actor scope，不信任呼叫端傳入值。
- 華語／英語 managed adapter 與台語／客語 SageMaker adapter（`sagemaker/`）只有程式與本機測試；
  WebSocket binary transport、production credential、真實 endpoint、成本與 quality gate 未完成，
  不得描述成 production 語音路徑。真人麥克風與聽感驗收見
  [`manual-voice-acceptance.md`](../../docs/runbooks/manual-voice-acceptance.md)。

## 執行與測試

```powershell
cd services/speech-gateway
uv sync --extra test --extra dev
uv run pytest            # contract boundary test 不需資料庫、雲端憑證或網路
uv run ruff check .
uv run ruff format --check .
# 本機啟動：pyproject 設 tool.uv.package = false，不可省略 --app-dir src
uv run uvicorn --app-dir src speech_gateway.app:app --reload --port 8002
```
