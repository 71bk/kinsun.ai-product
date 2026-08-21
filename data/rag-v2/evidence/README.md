# Generated Test Evidence

`v006/pytest-rag-ingestion.xml`, `v006/pytest-execution-receipt.json`, and
`v006/test-evidence.json` are the active evidence sources for the formal
RagChunkV2 audit. The test run embeds the active validation-input inventory
SHA-256 as a JUnit property. The receipt atomically records a portable display
command, the exact subprocess argv, exit code, timestamps, and JUnit SHA-256.
The evidence summary binds the receipt, JUnit, preflight inventory, and prior
artifact lock without modifying the immutable v002 candidate.

`v001/` through `v005/` remain immutable historical evidence. The v003 files
are still the package evidence copied into v002, but they no longer claim to
cover repository inputs added after that frozen run. The v004 run is preserved
as a failed audit attempt. The passing v005 run was superseded when the
human-review package contracts, implementation, and tests changed the frozen
validation input set.
