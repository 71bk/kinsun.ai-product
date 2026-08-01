from uuid import uuid4


def new_trace_id() -> str:
    return f"trace-{uuid4()}"


def new_agent_run_id() -> str:
    return f"run-{uuid4()}"
