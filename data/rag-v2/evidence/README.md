# Generated Test Evidence

`v003/pytest-rag-ingestion.xml` and
`v003/pytest-execution-receipt.json` are the active evidence sources for the
formal RagChunkV2 build. The test run embeds the active validation-input
inventory SHA-256 as a JUnit property. The receipt atomically records a
portable display command, the exact subprocess argv, exit code, timestamps,
and JUnit SHA-256. The builder refuses failed, empty, malformed, unbound,
partial, or stale evidence and copies both files into the checksummed candidate.

`v001/` and `v002/` remain immutable historical evidence. They predate the
current validator and test inputs and do not authorize the active candidate.
