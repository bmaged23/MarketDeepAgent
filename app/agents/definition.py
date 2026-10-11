from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class AgentDefinition:
    """Prompt and callable tools; execution orchestration belongs to the chat phase."""
    name: str
    system_prompt: str
    tools: dict[str, Callable]
