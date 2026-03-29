"""Shared Azure OpenAI LLM instance.

Supports two auth modes:
1. Local dev: AZURE_OPENAI_TOKEN env var (from az account get-access-token)
2. Production: AZURE_CLIENT_ID env var triggers ManagedIdentityCredential
"""

import os
from langchain_openai import AzureChatOpenAI

_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "https://demopresentations.services.ai.azure.com")
_deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5.4")
_token = os.environ.get("AZURE_OPENAI_TOKEN", "")

_auth_kwargs = {}

if _token:
    # Local dev: use pre-fetched token
    _auth_kwargs["azure_ad_token"] = _token
else:
    # Production: use managed identity via azure-identity
    try:
        from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
        client_id = os.environ.get("AZURE_CLIENT_ID")
        if client_id:
            credential = ManagedIdentityCredential(client_id=client_id)
        else:
            credential = DefaultAzureCredential()
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        _auth_kwargs["azure_ad_token"] = token.token
    except Exception as e:
        raise RuntimeError(
            f"No AZURE_OPENAI_TOKEN set and managed identity failed: {e}\n"
            "For local dev, run: $env:AZURE_OPENAI_TOKEN = az account get-access-token "
            "--resource https://cognitiveservices.azure.com --query accessToken -o tsv"
        )

llm = AzureChatOpenAI(
    azure_endpoint=_endpoint,
    azure_deployment=_deployment,
    **_auth_kwargs,
    api_version="2024-10-21",
    temperature=0.5,
    streaming=True,
    max_tokens=2000,
)
