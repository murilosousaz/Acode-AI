import os
import tempfile

import discord
from discord import app_commands
from discord.ext import commands

from src.app.use_cases.ingest_educational_material import IngestEducationalMaterialUseCase
from src.domain.value_objects.subject import Subject


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
    @app_commands.choices(materia=[
        app_commands.Choice(name=subject.label, value=subject.value) for subject in Subject
    ])
    @app_commands.default_permissions(administrator=True)
    async def ingest_pdf(
        self,
        interaction: discord.Interaction,
        arquivo: discord.Attachment,
        materia: app_commands.Choice[str],
        titulo: str
    ):
        # Usar as mesmas opções fixas do combobox de /duvida garante que o
        # texto gravado em metadata.subject seja idêntico ao usado no filtro
        # de busca vetorial — caso contrário, um material ingerido com um
        # texto livre poderia nunca ser encontrado.
        if not arquivo.filename.lower().endswith(".pdf"):
            await interaction.response.send_message("❌ O arquivo enviado deve ser um PDF.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        # Salva o anexo do Discord em um arquivo temporário local.
        # Usamos mkstemp + close do descritor antes de gravar (em vez de
        # manter o NamedTemporaryFile aberto) para evitar conflitos de
        # lock de arquivo em alguns sistemas operacionais.
        fd, temp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

        try:
            await arquivo.save(temp_path)

            inserted_count = await self.ingest_use_case.execute(
                pdf_path=temp_path,
                subject=materia.value,
                title=titulo
            )
            await interaction.followup.send(
                f" PDF **'{titulo}'** ({materia.name}) ingerido com sucesso!\n"
                f" Foram criados e vetorizados **{inserted_count}** blocos no MongoDB.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erro ao processar PDF: `{str(e)}`", ephemeral=True)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
