from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    GOOGLE_EMBEDDING_MODEL: str = "text-embedding-004"
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

    # text-embedding-004 do Google gera vetores de 768 dimensões (o da
    # OpenAI usado antes gerava 1536) — precisa bater com o índice vetorial
    # criado em scripts/create_vector_index.py.
    EMBEDDING_DIMENSIONS: int = 768

    # Máximo de comandos /duvida por usuário dentro da janela abaixo.
    RATE_LIMIT_REQUESTS: int = 5
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
