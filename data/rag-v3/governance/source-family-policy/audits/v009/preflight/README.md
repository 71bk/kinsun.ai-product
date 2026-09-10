# Source-family policy v002 law-repair projection audit v009

This successor preserves audit v001-v008 and binds the local v004 law-repair projection and runtime ID mapping to their implementation and tests.

- Current validation inputs: `118`
- Current inventory SHA-256: `d4d54937c954d1704a5e52aafeafe86d7370b267f942795c74f3531d92f3ae23`
- Historical artifact entries: `54`
- Historical lock SHA-256: `23184082db14d007d1cb83b5f9d531449cfdcd3bfe4accda58dc9550f31d06da`
- Runtime policy v003 decisions: unchanged
- Local projection candidate: 726 new IDs, only 71 governance corrections
- Runtime policy v004: pinned v003 response policy plus exact projection binding
- Live current/stop/eligibility/block/review gates: unchanged
- Remote OpenSearch transport: HTTPS with certificate and hostname validation
- Search execution: bounded concurrency, dedicated workers, shared deadline
- Cancellation: prompt caller cancellation with worker capacity retained until exit
- Historical inventories: sealed and validated independently of current HEAD
- External synchronization: not authorized
- Production: blocked
