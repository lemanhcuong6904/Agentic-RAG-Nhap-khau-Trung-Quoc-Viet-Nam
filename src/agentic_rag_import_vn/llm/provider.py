from __future__ import annotations

from dataclasses import dataclass

from agentic_rag_import_vn.config import settings


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str


class BaseLLMProvider:
    def generate(self, prompt: str) -> LLMResponse:
        raise NotImplementedError


class NoopLLMProvider(BaseLLMProvider):
    def generate(self, prompt: str) -> LLMResponse:
        return LLMResponse(text="", provider="none", model="")


class OpenAIProvider(BaseLLMProvider):
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("RAG_OPENAI_API_KEY is not set.")
        from openai import OpenAI

        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.llm_model

    def generate(self, prompt: str) -> LLMResponse:
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
            temperature=0.1,
        )
        return LLMResponse(text=response.output_text.strip(), provider="openai", model=self.model)


def get_llm_provider() -> BaseLLMProvider:
    if settings.llm_provider == "openai":
        return OpenAIProvider()
    return NoopLLMProvider()
