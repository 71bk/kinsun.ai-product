"""Keep the opt-in local verifier aligned with CI's migration isolation."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_local_verifier_runs_migrations_in_a_separate_process() -> None:
    script = (REPOSITORY_ROOT / "scripts/verify_core.ps1").read_text(encoding="utf-8")
    lines = [line.strip() for line in script.splitlines()]
    migration = "& $corePython -m pytest tests/integration/test_migrations.py"
    integration = (
        "& $corePython -m pytest tests/integration " "--ignore=tests/integration/test_migrations.py"
    )

    assert [line for line in lines if "& $corePython -m pytest tests/integration" in line] == [
        migration,
        integration,
    ]
    migration_index = lines.index(migration)
    assert lines[migration_index + 1] == (
        'Assert-NativeSuccess -Step "Core migration tests" -ExitCode $LASTEXITCODE'
    )
    assert lines[migration_index + 2] == integration
    assert lines[migration_index + 3] == (
        'Assert-NativeSuccess -Step "Core integration tests" -ExitCode $LASTEXITCODE'
    )


def test_local_verifier_keeps_opt_in_and_database_guard_before_tests() -> None:
    script = (REPOSITORY_ROOT / "scripts/verify_core.ps1").read_text(encoding="utf-8")

    assert "if (-not $ConfirmTestDatabaseMigrations)" in script
    assert 'EXPECTED_DATABASE = "kinsun_test"' in script
    assert 'ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}' in script
    assert "SELECT current_database()" in script
    guard = 'Assert-NativeSuccess -Step "Test database safety check" -ExitCode $LASTEXITCODE'
    assert script.index("if (-not $ConfirmTestDatabaseMigrations)") < script.index(guard)
    assert script.index(guard) < script.index("& $corePython -m pytest tests/unit")
