"""Bounded v004 staging sync. Default preflight; no document embedding provider.

The original temporary embedding artifact is unavailable. Reuse evidence is an
explicit new export of the current database, NOT verification against that lost
artifact. Both exports stay outside the repository. Apply rechecks the snapshot
digest under source row locks and commits projection + vectors atomically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import asdict, fields
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api"))

from app.database_url import to_psycopg_conninfo  # noqa: E402
from app.rag_embedding_importer import (  # noqa: E402
    EmbeddingProfileBinding,
    _parse_database_vector,
    import_embeddings,
    load_embedding_import_batch,
    verify_embeddings,
)
from app.rag_embedding_reuse_preflight import validate_embedding_reuse_snapshot  # noqa: E402
from app.rag_projection_importer import (  # noqa: E402
    ProjectionChunk,
    import_projection,
    load_projection_batch,
)

SOURCE_SHA = "bab68588963be5b47c7058f9cb9b5c0fd87181087316c262c9faefea6d5bedec"
TARGET_SHA = "f3339ceae77c380f42b3c2823b28216827ef48d057129a9c5f5edd40c9e808dd"
PROFILE_ID = "ep-google-00a12ec45096fa9d97d9e9b6"
AUTHORIZATION = ROOT / "docs/project/rag-law-sync-authorization-20260910.json"
AUTHORIZATION_SHA = "03fa69919b05d872e0885977f576d69f5ca8d4e6f88d6cf6188f5e54a526df0d"


class SyncValidationError(ValueError):
    """Only fixed internal codes may cross the command boundary."""


def encode(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, code):
    if not condition:
        raise SyncValidationError(code)


def load_inputs():
    base = ROOT / "data/rag-v2/candidates"
    source = load_projection_batch(
        base / "v002",
        ROOT / "contracts/schemas/rag/rag-chunk-v2.1.schema.json",
        expected_source_count=17,
        expected_chunk_count=726,
    )
    target = load_projection_batch(
        base / "v004",
        base / "v004/schemas/rag-law-repair-chunk-v004.schema.json",
        expected_source_count=17,
        expected_chunk_count=726,
    )
    require(
        source.candidate_sha256 == SOURCE_SHA and target.candidate_sha256 == TARGET_SHA,
        "CANDIDATE_PIN_MISMATCH",
    )
    require(
        sha(AUTHORIZATION.read_bytes()) == AUTHORIZATION_SHA,
        "AUTHORIZATION_PIN_MISMATCH",
    )
    auth = json.loads(AUTHORIZATION.read_bytes())
    require(
        auth["target_candidate_sha256"] == TARGET_SHA
        and auth["source_release_id"] == source.release_id
        and auth["target_release_id"] == target.release_id
        and auth["external_sync"] == "AUTHORIZED_AFTER_VALIDATION"
        and auth["production_approved"] is False,
        "AUTHORIZATION_MISMATCH",
    )
    crosswalk = {
        row["prior_chunk_id"]: row["chunk_id"]
        for row in (
            json.loads(line)
            for line in (base / "v004/crosswalk/chunk-id-crosswalk-v004.jsonl")
            .read_bytes()
            .splitlines()
        )
    }
    return source, target, crosswalk, sha(AUTHORIZATION.read_bytes())


def projection_rows(cursor, release_id, *, lock=False):
    columns = ["release_id"] + [field.name for field in fields(ProjectionChunk)]
    query = sql.SQL(
        "SELECT {} FROM rag_public.chunk_projection WHERE release_id = %s ORDER BY chunk_id{}"
    ).format(
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(" FOR SHARE" if lock else ""),
    )
    cursor.execute(query, (release_id,))
    return cursor.fetchall()


def read_snapshot(connection, source, *, lock=False):
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT artifact_version, candidate_sha256, source_count, chunk_count, "
            "release_status, review_status, human_source_review, production_approved, "
            "embedding_profile_id FROM rag_public.rag_release WHERE release_id = %s"
            + (" FOR SHARE" if lock else ""),
            (source.release_id,),
        )
        release = cursor.fetchone()
        expected = {
            key: getattr(source, key)
            for key in (
                "artifact_version",
                "candidate_sha256",
                "source_count",
                "chunk_count",
                "review_status",
                "human_source_review",
                "production_approved",
            )
        }
        expected.update(
            release_status="STAGING_CANDIDATE", embedding_profile_id=PROFILE_ID
        )
        require(encode(release) == encode(expected), "LIVE_RELEASE_DRIFT")
        cursor.execute(
            "SELECT provider, model_id, dimension, document_task_type, config_version "
            "FROM rag_public.embedding_profile WHERE embedding_profile_id = %s"
            + (" FOR SHARE" if lock else ""),
            (PROFILE_ID,),
        )
        profile = EmbeddingProfileBinding(**cursor.fetchone())
        require(profile.profile_id == PROFILE_ID, "LIVE_PROFILE_DRIFT")
        projections = projection_rows(cursor, source.release_id, lock=lock)
        expected_rows = [
            {"release_id": source.release_id, **asdict(row)}
            for row in sorted(source.chunks, key=lambda row: row.chunk_id)
        ]
        require(encode(projections) == encode(expected_rows), "LIVE_PROJECTION_DRIFT")
        cursor.execute(
            "SELECT release_id, chunk_id, embedding_profile_id, embedding_text_sha256, "
            "embedding::text AS embedding FROM rag_public.chunk_embedding "
            "WHERE release_id = %s ORDER BY chunk_id" + (" FOR SHARE" if lock else ""),
            (source.release_id,),
        )
        vectors = cursor.fetchall()
        require(len(vectors) == 726, "INCOMPLETE_VECTORS")
        cursor.execute(
            "SELECT operation, count(*) AS count FROM rag_public.ingestion_run "
            "WHERE release_id = %s AND candidate_sha256 = %s AND status = 'COMPLETED' "
            "AND failure_count = 0 GROUP BY operation",
            (source.release_id, SOURCE_SHA),
        )
        require(
            {row["operation"] for row in cursor.fetchall()}
            == {"PROJECT_CHUNKS", "EMBED_DOCUMENTS"},
            "SOURCE_RECEIPTS_MISSING",
        )
    return profile, projections, vectors


def export_batch(directory, projection, profile, vectors, *, crosswalk=None):
    version = projection.artifact_version
    allowlist_name = (
        "embedding-staging-allowlist-v003.json"
        if version == "v002"
        else "embedding-staging-allowlist-v004.json"
    )
    allowlist_sha = sha(
        (
            ROOT / f"data/rag-v2/candidates/{version}/manifests" / allowlist_name
        ).read_bytes()
    )
    manifest = dict(
        record_type="manifest",
        schema_version="2.0.0",
        allowlist_sha256=allowlist_sha,
        embedding_provider=profile.provider,
        embedding_model_id=profile.model_id,
        embedding_dimension=profile.dimension,
        document_task_type=profile.document_task_type,
        config_version=profile.config_version,
        chunk_count=projection.chunk_count,
    )
    payload = encode(manifest)
    for row in vectors:
        require(
            row["embedding_profile_id"] == profile.profile_id, "VECTOR_PROFILE_MISMATCH"
        )
        vector = _parse_database_vector(row["embedding"], profile.dimension)
        require(any(vector), "ZERO_VECTOR")
        payload += encode(
            dict(
                record_type="embedding",
                chunk_id=(crosswalk[row["chunk_id"]] if crosswalk else row["chunk_id"]),
                embedding_text_sha256=row["embedding_text_sha256"],
                allowlist_sha256=allowlist_sha,
                embedding_model_id=profile.model_id,
                embedding_dimension=profile.dimension,
                embedding=vector,
            )
        )
    artifact = directory / f"database-export-{version}.jsonl"
    with artifact.open("xb") as stream:
        stream.write(payload)
    batch = load_embedding_import_batch(
        artifact,
        repository_root=ROOT,
        projection=projection,
        expected_artifact_sha256=sha(payload),
        expected_allowlist_sha256=allowlist_sha,
        expected_profile_id=PROFILE_ID,
    )
    return batch, artifact


def run(
    connection,
    *,
    apply,
    expected_digest,
    directory,
    target_identity,
    verify_target=False,
):
    source, target, crosswalk, authorization_sha = load_inputs()
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        if not apply:
            connection.execute("SET TRANSACTION READ ONLY")
            require(
                connection.execute("SHOW transaction_read_only").fetchone()[0] == "on",
                "NOT_READ_ONLY",
            )
        connection.execute("SET LOCAL statement_timeout = '60s'")
        connection.execute("SET LOCAL lock_timeout = '5s'")
        profile, projections, vectors = read_snapshot(connection, source, lock=apply)
        original, source_path = export_batch(directory, source, profile, vectors)
        new, target_path = export_batch(
            directory, target, profile, vectors, crosswalk=crosswalk
        )
        evidence = validate_embedding_reuse_snapshot(
            source=source,
            target=target,
            original_embeddings=original,
            crosswalk=crosswalk,
            projection_rows=projections,
            embedding_rows=vectors,
        )
        evidence.update(
            authorization_sha256=authorization_sha,
            target_identity_sha256=target_identity,
            vector_evidence_origin="CURRENT_DATABASE_EXPORT_NOT_LOST_ORIGINAL_ARTIFACT",
        )
        digest = sha(encode(evidence))
        receipts = None
        if apply:
            require(expected_digest == digest, "PREFLIGHT_DRIFT")
            receipts = {
                "projection": import_projection(connection, target).to_dict(),
                "embeddings": import_embeddings(connection, new).to_dict(),
            }
        if apply or verify_target:
            if receipts is None:
                receipts = {}
            with connection.cursor(row_factory=dict_row) as cursor:
                actual = projection_rows(cursor, target.release_id)
            expected = [
                {"release_id": target.release_id, **asdict(row)}
                for row in sorted(target.chunks, key=lambda row: row.chunk_id)
            ]
            require(encode(actual) == encode(expected), "TARGET_READBACK_MISMATCH")
            receipts["verification"] = verify_embeddings(connection, new)
        # Assert all local pins again before the outer transaction can commit.
        require(load_inputs()[3] == authorization_sha, "AUTHORIZATION_CHANGED")
    return dict(
        status="COMMITTED"
        if apply
        else "VERIFIED"
        if verify_target
        else "PREFLIGHT_VALIDATED",
        preflight_sha256=digest,
        source_release_id=source.release_id,
        target_release_id=target.release_id,
        chunk_count=726,
        governance_changes=71,
        authorization_sha256=authorization_sha,
        target_identity_sha256=target_identity,
        vector_evidence_origin=evidence["vector_evidence_origin"],
        source_export_path=str(source_path),
        source_export_sha256=original.artifact_sha256,
        target_export_path=str(target_path),
        target_export_sha256=new.artifact_sha256,
        receipts=receipts,
        runtime_activated=False,
        production_approved=False,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "apply", "verify"))
    parser.add_argument("--expected-preflight-sha256")
    parser.add_argument("--confirm-staging-write", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "apply" and (
        not args.confirm_staging_write or not args.expected_preflight_sha256
    ):
        parser.error("apply requires confirmation and preflight digest")
    try:
        from dotenv import dotenv_values
        from sqlalchemy.engine import make_url

        config = {**dotenv_values(ROOT / ".env"), **os.environ}
        require(
            config.get("APP_ENV", "development").lower()
            in {"local", "development", "staging"},
            "STAGING_ONLY",
        )
        database = config.get("RAG_DATABASE_URL") or config["DATABASE_URL"]
        url = make_url(database)
        require(url.host and "supabase" in url.host, "EXPECTED_SUPABASE_TARGET")
        target_identity = sha(
            encode(
                dict(
                    host=url.host,
                    port=url.port,
                    database=url.database,
                    username=url.username,
                )
            )
        )
        directory = Path(tempfile.mkdtemp(prefix="kinsun-law-reuse-"))
        with psycopg.connect(
            to_psycopg_conninfo(database), connect_timeout=15
        ) as connection:
            report = run(
                connection,
                apply=args.command == "apply",
                expected_digest=args.expected_preflight_sha256,
                directory=directory,
                target_identity=target_identity,
                verify_target=args.command == "verify",
            )
        with (directory / "receipt.json").open("xb") as stream:
            stream.write(encode(report))
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception as exc:
        # No driver messages, connection strings, source contents or vectors.
        print(
            json.dumps(
                dict(
                    status="FAILED",
                    error_type=type(exc).__name__,
                    code=str(exc)
                    if isinstance(exc, SyncValidationError)
                    else "SYNC_VALIDATION_FAILED",
                    production_approved=False,
                )
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
