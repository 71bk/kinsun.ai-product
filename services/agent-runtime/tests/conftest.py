"""Keep the test suite deterministic and isolated from developer provider secrets."""

import os

# This runs before test modules import ``agent_runtime.app``. Tests must never
# inherit a real provider selected in the repository or service-local .env.
os.environ["APP_ENV"] = "test"
os.environ["MODEL_PROVIDER"] = "mock"
os.environ["SERVICE_IDENTITY_ENABLED"] = "true"
os.environ["SERVICE_IDENTITY_HMAC_SECRET"] = "synthetic-test-service-identity-secret-32-bytes"
