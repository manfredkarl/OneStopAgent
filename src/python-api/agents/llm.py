"""Shared Azure OpenAI LLM instance."""

import os
from langchain_openai import AzureChatOpenAI

# Token passed via AZURE_OPENAI_TOKEN env var (set before starting the server)
_token = os.environ.get("AZURE_OPENAI_TOKEN", "")
if not _token:
    raise RuntimeError("AZURE_OPENAI_TOKEN env var not set. Run: $env:AZURE_OPENAI_TOKEN = az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv")

llm = AzureChatOpenAI(
    azure_endpoint="https://demopresentations.services.ai.azure.com",
    azure_deployment="gpt-5.4",
    azure_ad_token=_token,
    api_version="2024-10-21",
    temperature=0.7,
    streaming=True,
)
