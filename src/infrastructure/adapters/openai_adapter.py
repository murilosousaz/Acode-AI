import asyncio
import logging
from typing import Dict, List, Optional

from openai import AsyncOpenAI, APIStatusError

logger = logging.getLogger(__name__)


class OpenAIAdapter:
    """Cliente para qualquer API compatível com o formato OpenAI.

    `base_url` permite apontar este mesmo adaptador para outros provedores
    compatíveis (ex.: DeepSeek em `https://api.deepseek.com`), mantendo a
    interface (`generate_embeddings`/`generate_chat_completion`) idêntica
    para a camada de aplicação. Quando omitido, usa o endpoint padrão da
    OpenAI.
    """

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def generate_embeddings(
        self,
        texts: List[str],
        model: str = "text-embedding-3-small",
        dimensions: Optional[int] = None,
        batch_size: int = 100,
        max_retries: int = 5,
    ) -> List[List[float]]:
        """Gera embeddings para uma lista de textos.

        O shim OpenAI-compatível do Gemini (`.../v1beta/openai/`) traduz a
        chamada `embeddings.create` internamente para uma
        `BatchEmbedContentsRequest` nativa, que aceita **no máximo 100
        entradas por lote**. PDFs inteiros geram bem mais chunks do que
        isso, então precisamos fatiar `texts` em lotes de até `batch_size`
        e concatenar os resultados, na ordem original.

        `dimensions` é repassado como o parâmetro `dimensions` do formato
        OpenAI (o Gemini mapeia isso para `output_dimensionality`). Modelos
        como `gemini-embedding-001` saem nativamente com 3072 dimensões,
        mas suportam truncar a saída (Matryoshka) — use isso para bater com
        a dimensão do índice vetorial já criado no MongoDB (ex.: 768),
        sem precisar recriar o índice a cada troca de modelo.

        Um 404 aqui pode ser transitório (raro) ou, com mais frequência,
        sinal de que o nome do modelo está errado/indisponível para essa
        chave — nesse segundo caso o retry vai só atrasar a falha, não
        evitá-la. Se o 404 for 100% reprodutível, confira o nome do modelo
        antes de mexer no retry.
        """
        if not texts:
            return []

        embeddings: List[List[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            embeddings.extend(
                await self._embed_batch_with_retry(batch, model, dimensions, max_retries)
            )
        return embeddings

    async def _embed_batch_with_retry(
        self, batch: List[str], model: str, dimensions: Optional[int], max_retries: int
    ) -> List[List[float]]:
        kwargs = {"input": batch, "model": model}
        if dimensions is not None:
            kwargs["dimensions"] = dimensions

        for attempt in range(1, max_retries + 1):
            try:
                response = await self.client.embeddings.create(**kwargs)
                return [data.embedding for data in response.data]
            except APIStatusError as e:
                # 400 (ex.: lote grande demais, parâmetro inválido) não se
                # resolve tentando de novo, então falha na hora.
                if e.status_code == 400 or attempt == max_retries:
                    raise
                wait = 2 ** attempt
                logger.warning(
                    "Erro %s ao gerar embeddings (tentativa %d/%d), tentando de novo em %ds: %s",
                    e.status_code, attempt, max_retries, wait, e,
                )
                await asyncio.sleep(wait)
        raise RuntimeError("unreachable")  # pragma: no cover

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
