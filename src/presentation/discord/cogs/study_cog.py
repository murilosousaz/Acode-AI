import discord
from discord import app_commands
from discord.ext import commands

from src.app.use_cases.answer_student_question import AnswerStudentQuestionUseCase
from src.domain.repositories.chat_repository import ChatRepository
from src.domain.value_objects.subject import Subject
from src.infrastructure.adapters.discord_formatter import DiscordFormatter
from src.infrastructure.adapters.rate_limiter import UserRateLimiter


class StudyCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        use_case: AnswerStudentQuestionUseCase,
        chat_repo: ChatRepository,
        rate_limiter: UserRateLimiter,
    ):
        self.bot = bot
        self.use_case = use_case
        self.chat_repo = chat_repo
        self.rate_limiter = rate_limiter

    @app_commands.command(name="duvida", description="Tire suas dúvidas sobre conteúdos do vestibular.")
    @app_commands.describe(
        pergunta="Digite sua dúvida ou pedido de explicação",
        materia="Selecione a matéria para filtrar o material (opcional)",
    )
    @app_commands.choices(materia=[
        app_commands.Choice(name=subject.label, value=subject.value) for subject in Subject
    ])
    async def duvida(
        self,
        interaction: discord.Interaction,
        pergunta: str,
        materia: app_commands.Choice[str] | None = None,
    ):
        user_id = str(interaction.user.id)

        if not self.rate_limiter.is_allowed(user_id):
            wait_seconds = int(self.rate_limiter.seconds_until_next_slot(user_id)) + 1
            await interaction.response.send_message(
                f"⏳ Você atingiu o limite de perguntas por minuto. "
                f"Tente novamente em {wait_seconds}s.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)

        subject_filter = materia.value if materia else None

        try:
            answer = await self.use_case.execute(
                user_id=user_id,
                question=pergunta,
                subject=subject_filter,
            )

            chunks = DiscordFormatter.split_message(answer)
            await interaction.followup.send(chunks[0])

            # Se houver mais partes na resposta devido ao tamanho
            for chunk in chunks[1:]:
                await interaction.channel.send(chunk)

        except Exception as e:
            await interaction.followup.send(f"❌ Ocorreu um erro ao processar sua dúvida: `{str(e)}`")

    @app_commands.command(name="limpar_historico", description="Reseta o histórico de conversas com o tutor.")
    async def limpar_historico(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        await self.chat_repo.clear_history(user_id)
        await interaction.response.send_message(
            "✅ Histórico de conversas zerado com sucesso! Agora podemos começar um novo assunto.",
            ephemeral=True,
        )
