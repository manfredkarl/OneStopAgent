"""Shared Azure OpenAI LLM instance."""

from langchain_openai import AzureChatOpenAI
from azure.identity import AzureCliCredential, get_bearer_token_provider

# Use AzureCliCredential specifically — DefaultAzureCredential picks wrong tenant
token_provider = get_bearer_token_provider(
    AzureCliCredential(),
    "https://cognitiveservices.azure.com/.default",
)

llm = AzureChatOpenAI(
    azure_endpoint="https://demopresentations.services.ai.azure.com",
    azure_deployment="gpt-4.1",
    azure_ad_token_provider=token_provider,
    api_version="2024-10-21",
    temperature=0.7,
    streaming=True,
)
