"""HerAndHim — Your virtual AI partner (boyfriend or girlfriend) on Telegram."""

from . import config
from .core.agent import Agent
from .core.llm.base import LLMProvider
from .core.llm.openai_compatible import OpenAICompatibleProvider
from .init import init

__version__ = "0.3.0"
__all__ = [
    "Agent",
    "LLMProvider",
    "OpenAICompatibleProvider",
    "config",
    "init",
    "__version__",
]
