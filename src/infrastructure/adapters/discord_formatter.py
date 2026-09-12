from typing import List


class DiscordFormatter:
    @staticmethod
    def split_message(text: str, max_length: int = 1900) -> List[str]:
        """Divide um texto longo em pedaços que caibam em mensagens do Discord.

        Tenta preservar quebras de linha ao dividir, mas se uma única linha
        for maior que ``max_length`` (ex.: um parágrafo sem quebras vindo do
        modelo), ela também é quebrada em pedaços fixos. Sem esse tratamento,
        uma linha muito longa produziria um chunk maior que o limite da API
        do Discord (2000 caracteres), causando erro HTTP 400 ao enviar.
        """
        if len(text) <= max_length:
            return [text]

        chunks: List[str] = []
        current_chunk = ""

        for line in text.split("\n"):
            while len(line) > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                chunks.append(line[:max_length])
                line = line[max_length:]

            if len(current_chunk) + len(line) + 1 <= max_length:
                current_chunk += line + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = line + "\n"

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks
