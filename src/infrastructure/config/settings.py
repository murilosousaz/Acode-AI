from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Campos que não podem ficar em branco no .env, mesmo sendo `str` (o
# Pydantic aceita "" como string válida, então sem essa checagem o erro só
# aparece depois, de forma confusa, dentro do SDK que consome a chave).
_REQUIRED_NON_EMPTY = ("DISCORD_BOT_TOKEN", "MONGO_URI", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY")


class Settings(BaseSettings):
    DISCORD_BOT_TOKEN: str
    MONGO_URI: str
    MONGO_DB_NAME: str = "acode-ai"
    # Chave do Google AI Studio (aistudio.google.com/apikey), usada só para
    # gerar embeddings. O Gemini expõe um endpoint compatível com o formato
    # da OpenAI, então reaproveitamos o mesmo OpenAIAdapter apontando para
    # outro base_url — igual fazemos com o DeepSeek para o chat.
    GOOGLE_API_KEY: str
    GOOGLE_EMBEDDING_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    GOOGLE_EMBEDDING_MODEL: str = "gemini-embedding-001"
    # Usadas apenas pelo docker-compose.yml para subir o container do
    # MongoDB local (lidas diretamente do shell/`.env` pelo Compose, não
    # pelo código Python). Ficam aqui como opcionais só para não quebrar a
    # inicialização do bot quando ele roda contra um Atlas remoto, sem
    # subir o container local.
    MONGO_ROOT_USERNAME: Optional[str] = None
    MONGO_ROOT_PASSWORD: Optional[str] = None

    # Chave da DeepSeek (platform.deepseek.com), usada para o chat do bot.
    # A API da DeepSeek também é compatível com o formato da OpenAI.
    DEEPSEEK_API_KEY: str
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    # deepseek-v4-pro = modo "thinking", melhor qualidade de resposta.
    # deepseek-v4-flash = mais rápido/barato, qualidade um pouco menor.
    DEEPSEEK_CHAT_MODEL: str = "deepseek-v4-pro"

    # gemini-embedding-001 sai nativamente com 3072 dimensões, mas suporta
    # truncar via Matryoshka (parâmetro `dimensions` na chamada) — usamos
    # 768 pra manter compatibilidade com o índice vetorial já existente,
    # criado em scripts/create_vector_index.py.
    EMBEDDING_DIMENSIONS: int = 768

    # Máximo de comandos /duvida por usuário dentro da janela abaixo.
    RATE_LIMIT_REQUESTS: int = 5
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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
