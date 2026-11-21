from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Campos que não podem ficar em branco no .env (o Pydantic aceita "" como
# string válida, então sem essa checagem o erro só aparece depois, de forma
# confusa, dentro do SDK que consome o valor).
_REQUIRED_NON_EMPTY = ("MONGO_URI",)


class Settings(BaseSettings):
    MONGO_URI: str
    MONGO_DB_NAME: str = "acode-ai"
    # Usadas apenas pelo docker-compose.yml para subir o container do
    # MongoDB local (lidas diretamente do shell/`.env` pelo Compose, não
    # pelo código Python). Ficam aqui como opcionais só para não quebrar a
    # inicialização do bot quando ele roda contra um Atlas remoto, sem
    # subir o container local.
    MONGO_ROOT_USERNAME: Optional[str] = None
    MONGO_ROOT_PASSWORD: Optional[str] = None

    # Ollama (https://ollama.com) — roda os modelos localmente, sem custo e
    # sem chave de API. O Ollama expõe um endpoint compatível com o formato
    # da OpenAI em `/v1`, então reaproveitamos o mesmo OpenAIAdapter para
    # embeddings e chat.
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    # Modelo de chat. Qualquer modelo de `ollama list` serve; qwen2.5:7b vai
    # bem em português. Para máquinas mais fracas, use `llama3.2:3b`.
    OLLAMA_CHAT_MODEL: str = "qwen2.5:7b"
    # Modelo de embeddings. nomic-embed-text gera vetores de 768 dimensões
    # (mesma dimensão do índice vetorial já criado em
    # scripts/create_vector_index.py).
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    # Limite de tokens da resposta do chat.
    OLLAMA_MAX_TOKENS: int = 2048
    # Tempo máximo (s) esperando o Ollama. Modelos locais podem ser lentos,
    # principalmente na primeira chamada (carregando o modelo na memória).
    OLLAMA_TIMEOUT_SECONDS: float = 180.0

    # Dimensão esperada do vetor de embedding. Usada no índice vetorial do
    # MongoDB e para validar a saída do modelo de embeddings. Se trocar de
    # modelo, ajuste este valor e recrie o índice + reingira os PDFs.
    EMBEDDING_DIMENSIONS: int = 768

    # Máximo de perguntas por cliente (IP) dentro da janela abaixo.
    RATE_LIMIT_REQUESTS: int = 5
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Chave exigida (header `X-API-Key`) nos endpoints administrativos, como
    # o upload de PDFs. Se vazia, esses endpoints ficam desabilitados.
    ADMIN_API_KEY: Optional[str] = None
    # Origens do frontend autorizadas pelo CORS, separadas por vírgula.
    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    # Tamanho máximo do PDF enviado, em MB.
    MAX_UPLOAD_MB: int = 25
    # Serve a pasta `frontend/` em "/" (mesma origem da API, sem CORS). Desligue
    # se o frontend for hospedado separadamente.
    SERVE_FRONTEND: bool = True

    # `extra="ignore"` evita erro caso o .env antigo ainda tenha variáveis
    # removidas (DISCORD_BOT_TOKEN, GOOGLE_API_KEY, DEEPSEEK_*...).
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOW_ORIGINS.split(",") if o.strip()]

    @field_validator(*_REQUIRED_NON_EMPTY)
    @classmethod
    def _not_blank(cls, value: str, info) -> str:
        if not value or not value.strip():
            raise ValueError(
                f"'{info.field_name}' está vazio no .env — preencha com um valor real "
                f"(veja .env.example) antes de rodar o projeto."
            )
        return value


settings = Settings()
