# legacy/

本目錄收放已依 [ADR 0007](../docs/adr/0007-canonical-backend-and-aws-deployment-authority.md)
定案為 legacy 的程式碼。這裡的內容是**凍結狀態**：不加新功能、不修 bug、不部署、不列入
一般 CI／typecheck／test 範圍。

## backend/

原路徑 `packages/backend`（2026-08-06 目錄重整時以 `git mv` 搬移到此處，rename history
可用 `git log --follow` 查）。ADR 0007 已將它與現有 `infrastructure/lib/elderly-care-stack.ts`
一併定為 legacy：不加入新功能，也不得部署現有 Lambda／DynamoDB／另一套 Cognito stack。
一般 HTTP 主線只走 Next.js BFF → Python Core → Agent Runtime。

搬出 npm workspaces（根 `package.json` 的 `"workspaces": ["packages/*", "infrastructure"]`
glob 不再命中 `legacy/backend`）之後，本目錄底下大量檔案的
`import type ... from '@elderly-care/shared'` **不再能解析**——這是預期行為，不是搬移
造成的迴歸。因為這是凍結程式碼、不再參與 typecheck／test，所以刻意不去修這些 import；
修了反而會讓人誤以為這段程式碼仍在維護。

要看這段程式碼在凍結前的完整歷史、或它與 `packages/shared`／`infrastructure/` 曾經如何
串接，請查 git log（例如 `git log --follow -- legacy/backend` 或直接看搬移前的 commit）。

`packages/shared` 維持原位，未搬入本目錄——它同時被 `packages/frontend` 與這裡的 legacy
backend 使用，前端仍在用中，不屬於凍結範圍。
