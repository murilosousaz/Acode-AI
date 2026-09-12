import asyncio
import logging

import discord
from discord.ext import commands

from src.infrastructure.config.settings import settings
from src.infrastructure.database.mongodb.connection import (
    connect_to_mongo,
    close_mongo_connection,
    db_context,
)
from src.infrastructure.database.mongodb.mongo_document_repo import MongoDocumentRepository
from src.infrastructure.database.mongodb.mongo_chat_repo import MongoChatRepository
from src.infrastructure.adapters.openai_adapter import OpenAIAdapter
from src.infrastructure.adapters.rate_limiter import UserRateLimiter

from src.app.use_cases.answer_student_question import AnswerStudentQuestionUseCase
from src.app.use_cases.ingest_educational_material import IngestEducationalMaterialUseCase

from src.presentation.discord.cogs.study_cog import StudyCog
from src.presentation.discord.cogs.admin_cog import AdminCog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("acodeai")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logger.info("🤖 AcodeAI no ar como %s (ID: %s)", bot.user.name, bot.user.id)
    try:
        synced = await bot.tree.sync()
        logger.info("⚡ Sincronizados %d comando(s) slash!", len(synced))
    except Exception:
        logger.exception("❌ Erro ao sincronizar slash commands.")


async def main():
    await connect_to_mongo()

    doc_repo = MongoDocumentRepository(db_context.db)
    chat_repo = MongoChatRepository(db_context.db)
    openai_adapter = OpenAIAdapter(api_key=settings.OPENAI_API_KEY)
    rate_limiter = UserRateLimiter(
        requests_limit=settings.RATE_LIMIT_REQUESTS,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )

    rag_use_case = AnswerStudentQuestionUseCase(
        doc_repo,
        chat_repo,
        openai_adapter,
        chat_model=settings.OPENAI_CHAT_MODEL,
        embedding_model=settings.OPENAI_EMBEDDING_MODEL,
    )
    ingest_use_case = IngestEducationalMaterialUseCase(
        doc_repo,
        openai_adapter,
        embedding_model=settings.OPENAI_EMBEDDING_MODEL,
    )

    await bot.add_cog(StudyCog(bot, rag_use_case, chat_repo, rate_limiter))
    await bot.add_cog(AdminCog(bot, ingest_use_case))

    try:
        await bot.start(settings.DISCORD_BOT_TOKEN)
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
