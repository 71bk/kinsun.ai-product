from pydantic import Field

from agent_runtime.contracts.models import ContractBaseModel


class CompanionOutput(ContractBaseModel):
    reply_text: str = Field(min_length=1, max_length=4000)
