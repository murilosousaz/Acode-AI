from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DISCORD_BOT_TOKEN: str
    MONGO_URI: str
    MONGO_DB_NAME: str = "vestibot"
    OPENAI_API_KEY: str

    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    # Precisa bater com a dimensão de saída de OPENAI_EMBEDDING_MODEL, pois é
    # usada na definição do índice vetorial do MongoDB (scripts/create_vector_index.py).
    # Referência: text-embedding-3-small = 1536, text-embedding-3-large = 3072,
    # text-embedding-ada-002 = 1536.
    EMBEDDING_DIMENSIONS: int = 1536

    # Máximo de comandos /duvida por usuário dentro da janela abaixo.
    RATE_LIMIT_REQUESTS: int = 5
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
