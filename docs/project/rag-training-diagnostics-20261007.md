# Source-backed training-hour diagnostics — 2026-10-07

The previously reported training-hour gap came from an unsupported synthetic question. Its two named courses are absent from the frozen A unit manual. The existing v009 retriever had already selected course tables, and returning NO_DATA was appropriate. With actual source course names, three questions now answer successfully and all five checked course/hour pairs match the tables. The final development BFF verification passed 19/19 checks.

PR [#74](https://github.com/71bk/kinsun.ai-product/pull/74) is merged as `628015a`; all ten checks in its [Gate 1 run](https://github.com/71bk/kinsun.ai-product/actions/runs/37560172833) passed. This follow-up changes developer cases and documentation. Runtime retrieval, generation, admission, citations and safety rules remain unchanged.

## Question correction and source facts

The old case asked for hours for 「長照政策與理念概述」 and 「A單位個案管理工作內容」 in a purported basic course. Neither title occurs in the frozen corpus, including after whitespace-only comparison for diagnostic lookup. No authoritative equivalence to similarly named courses is recorded. Its original `answer` expectation was wrong; assigning hours from a nearby course would invent the mapping.

The original question is preserved verbatim as `case-manager-training`, now an unsupported-name negative case. [Layout diagnostic cases](../../config/rag/knowledge-layout-smoke-queries.json) advance from `v009-layout-20261006-v1` to `v009-layout-20261007-v2`, retaining the CA07/CB01 and family CA07 cases and adding three source-backed training positives and one family counterpart. There are eight cases. The earlier v1 report and its NO_DATA result remain historical evidence.

Expected numbers were read from complete physical table rows in the checked-in [frozen extraction](../../data/rag-layout/v001/extraction.jsonl):

| Course | Physical PDF page | Hours |
| --- | --- | --- |
| 社區整合型服務中心個管人員的角色功能與職掌 | 137 | 1 |
| 個案管理與服務品質 | 137 | 3 |
| 長照相關資訊系統及實務操作 | 137 | 1 |
| 溝通與協調, Level II | 141 | 1 |
| 感染管制, Level II | 141 | 2 |

The positive questions explicitly refer to the 2023 manual. Source date/currency warnings are retained; these checks do not establish that the course requirements are current today. Diagnostic lookup may remove whitespace to identify a table label; production source-span/citation validation is unchanged.

## Live verification

The final direct run used the existing 713-chunk `knowledge-v009-5046fa3d59c4` release, with a read-only preflight confirming release/profile/vector bindings. It made five query-embedding and five generation calls: three SUCCESS and two NO_DATA. The three positives each selected one citation and validated 11, 7 and 6 source spans respectively. All five named course/hour pairs matched their source rows. The unchanged unsupported-name question returned NO_DATA; the family counterpart returned NO_DATA and retrieved no professional-only v009 repair fragments.

The final BFF run passed 19/19 checks with synthetic family/staff accounts:

- Anonymous access, login, cross-role rejection, caller-supplied audience rejection, CSRF and logout for both roles.
- Three staff training positives returned ANSWER, each with one official repaired-source citation and matching course/hour pairs, in 9,844 / 7,000 / 6,578 ms.
- The original unsupported-name question and family training counterpart returned NO_DATA without citations.
- Both roles' medication questions returned BLOCKED.

An initial direct attempt ended with TimeoutError before creating a report. The instrumented recheck passed its read-only preflight in 1,453 ms. An earlier authentication-only helper completed its checks but failed to write its report because the fresh ignored output directory was absent; the final BFF run created and wrote its report successfully. An initial local family assertion also incorrectly excluded the entire A manual source; the corrected check follows existing audience scope and excludes only the professional repair fragments, while preserving already permitted family records. These earlier attempts are not counted as successful complete runs.

The ignored local evidence is `.rag-work/training-live-v2.json`, `.rag-work/training-outcomes-v2.json` and `.rag-work/training-bff-outcomes.json`. No raw model replies, prompts, credentials or upstream exception strings are copied into this report or committed. Numeric-pair checks and citation anchors are targeted observations, not general semantic accuracy measurements or human source review.

## Daily development synchronization

All 409 tracked Python/TypeScript files in the Agent source, Core application and frontend server directories now match merged main after normalized line-ending comparison. Only the two frontend files missing PR #74's changes were copied, after proving their daily versions matched pre-PR main. Thirteen merged RAG source/schema/config/documentation files were also copied when absent or matching a known pre-merge base. User changes outside this scope and the daily branch were preserved.

Frontend 3000 continues to run the already verified isolated build; its checkout tree is identical to merged main. Core 8000 and Agent 8001 continue with the matching daily source. No new service build/restart is needed for this configuration-only diagnostic update. Development stays on v009 with V3 and Core router v2 enabled. No new embeddings, database import, environment-setting change or production activation was performed.

The eight updated cases pass the existing offline loader/selection plan without loading private settings or calling providers. Production remains disabled and source review remains `needs_review` / `not_completed`. The fixed original 16-question evaluation was not rerun or recomputed from these separate targeted checks.
