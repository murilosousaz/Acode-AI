import asyncio
import logging
from typing import AsyncIterator, Dict, List, Optional

from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from src.domain.errors import AIServiceUnavailableError
from src.domain.ports import EmbeddingPurpose

logger = logging.getLogger(__name__)


class OllamaAdapter:
    """Cliente do Ollama via endpoint compatível com OpenAI (`/v1`).

    Implementa as portas `EmbeddingGenerator` e `ChatCompleter`. Os modelos
    ficam configurados no adaptador, então os casos de uso não precisam
    conhecer nomes de modelo nem detalhes do provedor.
    """

    def __init__(
        self,
        base_url: str,
        chat_model: str,
        embedding_model: str,
        embedding_dimensions: Optional[int] = None,
        max_tokens: int = 2048,
        timeout: float = 180.0,
        embedding_batch_size: int = 32,
        max_retries: int = 3,
        query_prefix: str = "",
        document_prefix: str = "",
    ):
        # O Ollama ignora a chave, mas o SDK exige um valor não vazio.
        # max_retries=0 no SDK: as tentativas são controladas aqui, para que
        # um Ollama fora do ar não multiplique o tempo de espera do usuário.
        self.client = AsyncOpenAI(
            api_key="ollama", base_url=base_url, timeout=timeout, max_retries=0
        )
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions
        self.max_tokens = max_tokens
        self.embedding_batch_size = embedding_batch_size
        self.max_retries = max_retries
        # Prefixos de tarefa (ex.: nomic-embed-text: "search_query:" / "search_document:").
        # Vazio = sem prefixo (comportamento anterior).
        self.query_prefix = self._normalize_prefix(query_prefix)
        self.document_prefix = self._normalize_prefix(document_prefix)

    @staticmethod
    def _normalize_prefix(prefix: Optional[str]) -> str:
        """"search_query:" e "search_query: " viram a mesma coisa (um espaço depois dos dois pontos).
        O espaço final se perderia num .env sem aspas."""
        prefix = (prefix or "").strip()
        return f"{prefix} " if prefix else ""

    # ------------------------------------------------------------------ embeddings
    async def generate_embeddings(
        self, texts: List[str], purpose: EmbeddingPurpose = "document"
    ) -> List[List[float]]:
        """Gera embeddings em lotes. Valida a dimensão do vetor: se o modelo
        devolver um tamanho diferente de `embedding_dimensions` (ex.: trocou o
        modelo mas não o índice vetorial), falha com mensagem clara em vez de
        gravar/consultar vetores incompatíveis."""
        if not texts:
            return []

        prefix = self.query_prefix if purpose == "query" else self.document_prefix
        if prefix:
            texts = [prefix + t for t in texts]

        embeddings: List[List[float]] = []
        size = self.embedding_batch_size
        total_batches = -(-len(texts) // size)
        for n, start in enumerate(range(0, len(texts), size), start=1):
            embeddings.extend(await self._embed_batch(texts[start:start + size]))
            if total_batches > 1:
                logger.info("Embeddings: lote %d/%d concluído.", n, total_batches)

        got = len(embeddings[0])
        if self.embedding_dimensions is not None and got != self.embedding_dimensions:
            raise ValueError(
                f"O modelo '{self.embedding_model}' devolveu vetores de {got} "
                f"dimensões, mas EMBEDDING_DIMENSIONS={self.embedding_dimensions}. "
                "Ajuste a variável, recrie o índice vetorial e reingira os PDFs."
            )
        return embeddings

    async def _embed_batch(self, batch: List[str]) -> List[List[float]]:
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self.client.embeddings.create(
                    input=batch, model=self.embedding_model
                )
                return [item.embedding for item in response.data]
            except APIStatusError as e:
                if e.status_code == 404:
                    raise self._model_not_found(self.embedding_model, e) from e
                # 4xx (exceto 404) não se resolve tentando de novo.
                if e.status_code < 500:
                    raise
                if attempt == self.max_retries:
                    raise self._service_error(e) from e
                wait = 2 ** attempt
                logger.warning(
                    "Erro %s ao gerar embeddings (tentativa %d/%d), nova tentativa em %ds.",
                    e.status_code, attempt, self.max_retries, wait,
                )
                await asyncio.sleep(wait)
            except APIConnectionError as e:
                raise self._unreachable(e) from e
        raise RuntimeError("unreachable")  # pragma: no cover

    # ------------------------------------------------------------------ chat
    async def generate_chat_completion(
        self, messages: List[Dict[str, str]], temperature: float = 0.3
    ) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                temperature=temperature,
                max_tokens=self.max_tokens,
            )
        except APIStatusError as e:
            if e.status_code == 404:
                raise self._model_not_found(self.chat_model, e) from e
            if e.status_code >= 500:
                raise self._service_error(e) from e
            raise
        except APIConnectionError as e:
            raise self._unreachable(e) from e

        message = response.choices[0].message
        content = getattr(message, "content", None)

        # Modelos "thinking" (ex.: deepseek-r1, qwen3 no Ollama) separam o
        # raciocínio (reasoning_content) da resposta final. Se forem cortados
        # no meio do raciocínio, `content` vem vazio: usamos o raciocínio como
        # fallback em vez de devolver uma resposta vazia.
        if content is None or not content.strip():
            reasoning = getattr(message, "reasoning_content", None)
            if reasoning and reasoning.strip():
                logger.warning(
                    "Resposta final vazia; usando reasoning_content como fallback. "
                    "Considere aumentar OLLAMA_MAX_TOKENS."
                )
                return reasoning.strip()
            raise AIServiceUnavailableError(
                "O modelo devolveu uma resposta vazia. Aumente OLLAMA_MAX_TOKENS "
                "ou verifique o modelo."
            )
        return content.strip()

    async def stream_chat_completion(
        self, messages: List[Dict[str, str]], temperature: float = 0.3
    ) -> AsyncIterator[str]:
        """Resposta do modelo aos pedaços. Mesmos erros de `generate_chat_completion`.

        Só o texto final é entregue: o raciocínio de modelos "thinking" não é transmitido
        (nesse caso o aluno vê a espera inicial mais longa, não o "pensamento").
        """
        produced = False
        try:
            stream = await self.client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                temperature=temperature,
                max_tokens=self.max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                piece = getattr(chunk.choices[0].delta, "content", None)
                if not piece:
                    continue
                if not produced:
                    piece = piece.lstrip()  # modelos costumam abrir com quebra de linha/espaço
                    if not piece:
                        continue
                    produced = True
                yield piece
        except APIStatusError as e:
            if e.status_code == 404:
                raise self._model_not_found(self.chat_model, e) from e
            if e.status_code >= 500:
                raise self._service_error(e) from e
            raise
        except APIConnectionError as e:
            raise self._unreachable(e) from e

        if not produced:
            raise AIServiceUnavailableError(
                "O modelo devolveu uma resposta vazia. Aumente OLLAMA_MAX_TOKENS "
                "ou verifique o modelo."
            )

    # ------------------------------------------------------------------ health
    async def ping(self) -> None:
        """Levanta AIServiceUnavailableError se o Ollama não responder."""
        try:
            await self.client.models.list()
        except (APIConnectionError, APIStatusError) as e:
            raise self._unreachable(e) from e

    # ------------------------------------------------------------------ erros
    @staticmethod
    def _unreachable(cause: Exception) -> AIServiceUnavailableError:
        return AIServiceUnavailableError(f"Ollama inacessível ou lento demais: {cause}")

    @staticmethod
    def _service_error(cause: APIStatusError) -> AIServiceUnavailableError:
        return AIServiceUnavailableError(f"Ollama respondeu com erro {cause.status_code}: {cause}")

    @staticmethod
    def _model_not_found(model: str, cause: Exception) -> AIServiceUnavailableError:
        return AIServiceUnavailableError(
            f"Modelo '{model}' não encontrado no Ollama. Rode `ollama pull {model}`."
        )
