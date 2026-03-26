import { DefaultAzureCredential } from '@azure/identity';

const ENDPOINT = process.env.AZURE_OPENAI_ENDPOINT || 'https://demopresentations.services.ai.azure.com';
const DEPLOYMENT = process.env.AZURE_OPENAI_DEPLOYMENT || 'gpt-4.1';
const API_VERSION = '2024-10-21';

const credential = new DefaultAzureCredential();

let cachedToken: { token: string; expiresOn: number } | null = null;

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface LlmOptions {
  temperature?: number;
  maxTokens?: number;
  responseFormat?: 'text' | 'json_object';
}

/**
 * Call Azure OpenAI chat completions using DefaultAzureCredential (az login / managed identity).
 */
export async function chatCompletion(
  messages: ChatMessage[],
  options: LlmOptions = {},
): Promise<string> {
  // Get or refresh token (cache for 5 minutes)
  if (!cachedToken || cachedToken.expiresOn < Date.now()) {
    const result = await credential.getToken('https://cognitiveservices.azure.com/.default');
    cachedToken = { token: result.token, expiresOn: Date.now() + 5 * 60 * 1000 };
  }
  
  const body: Record<string, unknown> = {
    messages,
    max_tokens: options.maxTokens ?? 4096,
    temperature: options.temperature ?? 0.7,
  };

  if (options.responseFormat === 'json_object') {
    body.response_format = { type: 'json_object' };
  }

  const url = `${ENDPOINT}/openai/deployments/${DEPLOYMENT}/chat/completions?api-version=${API_VERSION}`;

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${cachedToken.token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(60_000),
  });

  if (!res.ok) {
    const err = await res.text().catch(() => '');
    throw new Error(`Azure OpenAI error ${res.status}: ${err}`);
  }

  const data = await res.json() as { choices: { message: { content: string } }[] };
  return data.choices[0]?.message?.content ?? '';
}
