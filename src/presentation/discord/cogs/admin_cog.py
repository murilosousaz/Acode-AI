import os
import tempfile
import discord
from discord import app_commands
from discord.ext import commands
from src.app.use_cases.ingest_educational_material import IngestEducationalMaterialUseCase

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot, ingest_use_case: IngestEducationalMaterialUseCase):
        self.bot = bot
        self.ingest_use_case = ingest_use_case

    @app_commands.command(name="ingest_pdf", description="[Admin] Adiciona uma apostila/prova PDF ao banco de dados.")
    @app_commands.describe(
        arquivo="O arquivo PDF a ser ingerido",
        materia="A matéria referente ao material",
        titulo="Título descritivo do documento"
    )
    @app_commands.default_permissions(administrator=True)
    async def ingest_pdf(
        self,
        interaction: discord.Interaction,
        arquivo: discord.Attachment,
        materia: str,
        titulo: str
    ):
        if not arquivo.filename.endswith(".pdf"):
            await interaction.response.send_message("❌ O arquivo enviado deve ser um PDF.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        # Salva o anexo do Discord em um arquivo temporário local
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            await arquivo.save(tmp_file.name)
            temp_path = tmp_file.name

        try:
            inserted_count = await self.ingest_use_case.execute(
                pdf_path=temp_path,
                subject=materia,
                title=titulo
            )
            await interaction.followup.send(
                f" PDF **'{titulo}'** ({materia}) ingerido com sucesso!\n"
                f" Foram criados e vetorizados **{inserted_count}** blocos no MongoDB.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erro ao processar PDF: `{str(e)}`", ephemeral=True)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)