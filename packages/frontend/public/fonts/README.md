# public/fonts — 自架字型

`MASTER.md` §5：Figtree（拉丁字母與數字）與 Noto Sans TC（中文）都必須從自有網域提供，
不得依賴 Google Fonts CDN（離線可用性＋不對外洩漏使用者 IP）。

| 字型 | 授權 | 來源 | 放在哪裡 |
| --- | --- | --- | --- |
| Figtree（可變字型，wght 300–900） | OFL 1.1（`LICENSE-Figtree.txt`） | `google/fonts` `ofl/figtree/Figtree[wght].ttf`，2026-09-15 取得 | `src/app/fonts/figtree-variable.woff2`，由 `next/font/local` 載入（`layout.tsx`） |
| Noto Sans TC（可變字型，wght 限制為 400–700） | OFL 1.1（`LICENSE-NotoSansTC.txt`） | `google/fonts` `ofl/notosanstc/NotoSansTC[wght].ttf`，2026-09-15 取得 | `noto-sans-tc/v1/*.woff2`，由 `src/app/fonts/noto-sans-tc.css` 的 `@font-face` 宣告 |

## Noto Sans TC 為什麼切片

整套可變字型約 12 MB，不能一次塞給長者的平板。`scripts/fonts/build_noto_sans_tc_slices.py`
把它依 Google Fonts 對 Noto Sans TC 公開的 unicode-range 邊界（`scripts/fonts/noto-sans-tc-unicode-ranges.json`）
切成約一百個小檔，瀏覽器只下載頁面用到的片段。切片時 wght 軸限制在 400–700（§5 只用
400／500／700），每片 `font-display: swap`。

## 重新產生

```powershell
python -m pip install fonttools brotli
python scripts/fonts/build_noto_sans_tc_slices.py --noto <NotoSansTC[wght].ttf> --figtree <Figtree[wght].ttf>
```

換版時把輸出目錄從 `v1` 升到 `v2` 並同步 `noto-sans-tc.css`：`next.config.mjs` 對
`/fonts/*` 設定一年 immutable 快取，靠路徑換版。

不要把 `.ttf` 原始檔或未切片的整套字型放進 repo。
