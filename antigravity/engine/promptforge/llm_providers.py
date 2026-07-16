from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


Message = Dict[str, str]


class LLMProvider:
    def complete(self, messages: List[Message], **kwargs: Any) -> str:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class ProviderConfig:
    name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_version: Optional[str] = None
    deployment: Optional[str] = None


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        raw = (base_url or "https://api.openai.com/v1").rstrip("/")
        # 兼容用户粘贴完整 chat/completions URL 或仅 host
        if raw.endswith("/chat/completions"):
            raw = raw[: -len("/chat/completions")]
        self.base_url = raw

    def complete(self, messages: List[Message], **kwargs: Any) -> str:
        payload = {
            "model": kwargs.get("model"),
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.0),
            "max_tokens": kwargs.get("max_tokens"),
        }
        # 去掉 None，避免部分兼容网关报错
        payload = {k: v for k, v in payload.items() if v is not None}
        if kwargs.get("response_format"):
            payload["response_format"] = kwargs["response_format"]
        url = f"{self.base_url}/chat/completions"
        response = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=kwargs.get("timeout", 120),
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"LLM 请求失败 HTTP {response.status_code}: {response.text[:300]} (url={url})"
            )
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"无法解析 LLM 响应: {str(data)[:300]}") from exc


class AzureOpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str, deployment: str, api_version: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.deployment = deployment
        self.api_version = api_version

    def complete(self, messages: List[Message], **kwargs: Any) -> str:
        params = {"api-version": self.api_version}
        payload = {
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.0),
            "max_tokens": kwargs.get("max_tokens"),
        }
        if kwargs.get("response_format"):
            payload["response_format"] = kwargs["response_format"]
        response = requests.post(
            f"{self.base_url}/openai/deployments/{self.deployment}/chat/completions",
            params=params,
            json=payload,
            headers={"api-key": self.api_key},
            timeout=kwargs.get("timeout", 30),
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


class DashScopeProvider(LLMProvider):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

    def complete(self, messages: List[Message], **kwargs: Any) -> str:
        payload = {
            "model": kwargs.get("model", "qwen-turbo"),
            "input": {"messages": messages},
            "parameters": {"temperature": kwargs.get("temperature", 0.0)},
        }
        response = requests.post(
            self.endpoint,
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=kwargs.get("timeout", 30),
        )
        response.raise_for_status()
        data = response.json()
        if "output" in data:
            if "text" in data["output"]:
                return data["output"]["text"].strip()
            choices = data["output"].get("choices") or []
            if choices:
                return choices[0]["message"]["content"].strip()
        raise RuntimeError(f"Unexpected DashScope response: {json.dumps(data, ensure_ascii=False)}")


class DummyProvider(LLMProvider):
    def complete(self, messages: List[Message], **kwargs: Any) -> str:
        raise RuntimeError("LLM provider not configured. Use --dry-run for offline mode or supply --llm-provider.")


class OfflineProvider(LLMProvider):
    def complete(self, messages: List[Message], **kwargs: Any) -> str:
        return "[]"


class LLMProviderFactory:
    @staticmethod
    def create(name: Optional[str], **kwargs: Any) -> Optional[LLMProvider]:
        if not name:
            return None
        name = name.lower()
        if name == "offline":
            return OfflineProvider()
        if name == "openai":
            api_key = kwargs.get("api_key") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY is not set.")
            return OpenAIProvider(api_key=api_key, base_url=kwargs.get("base_url"))
        if name == "azure":
            api_key = kwargs.get("api_key") or os.getenv("AZURE_OPENAI_KEY")
            base_url = kwargs.get("base_url") or os.getenv("AZURE_OPENAI_ENDPOINT")
            deployment = kwargs.get("deployment") or os.getenv("AZURE_OPENAI_DEPLOYMENT")
            api_version = kwargs.get("api_version") or os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
            if not all([api_key, base_url, deployment]):
                raise RuntimeError("Azure OpenAI信息不完整，请提供api-key/endpoint/deployment。")
            return AzureOpenAIProvider(api_key=api_key, base_url=base_url, deployment=deployment, api_version=api_version)
        if name == "dashscope":
            api_key = kwargs.get("api_key") or os.getenv("DASHSCOPE_API_KEY")
            if not api_key:
                raise RuntimeError("DASHSCOPE_API_KEY 未设置。")
            return DashScopeProvider(api_key=api_key)
        raise ValueError(f"Unsupported provider: {name}")
