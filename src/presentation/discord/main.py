import asyncio
import discord
from discord.ext import commands
from src.infrastructure.config.settings import settings
from src.infrastructure.database.mongodb.connection import (
    connect_to_mongo,
    close_mongo_connection,
)

intents = discord.Intents.default()
intents.message_content = True  

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🤖 Bot operacional como {bot.user.name} (ID: {bot.user.id})")
    await connect_to_mongo()

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("Pong! 🏓 O Vestibot está online e operando.")

async def main():
    try:
        async with bot:
            await bot.start(settings.DISCORD_BOT_TOKEN)
    finally:
        await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())