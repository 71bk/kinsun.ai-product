from dataclasses import dataclass


@dataclass(frozen=True)
class LoopController:
    system_limit: int

    def can_execute(self, request_limit: int, step: int) -> bool:
        return step <= min(request_limit, self.system_limit)
