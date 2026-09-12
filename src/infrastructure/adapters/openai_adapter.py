from typing import Dict, List

from openai import AsyncOpenAI


class OpenAIAdapter:
    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)

    async def generate_embeddings(
        self, texts: List[str], model: str = "text-embedding-3-small"
    ) -> List[List[float]]:
        if not texts:
            return []

        response = await self.client.embeddings.create(
            input=texts,
            model=model
        )
        return [data.embedding for data in response.data]

    async def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o-mini",
        temperature: float = 0.3,
    ) -> str:
        """Gera uma resposta de chat a partir de uma lista de mensagens.

        Mantém o cliente da OpenAI encapsulado neste adaptador, para que a
        camada de aplicação (use cases) não precise conhecer detalhes da
        API da OpenAI (ex.: `response.choices[0].message.content`).
        """
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()
