from typing import List
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