from typing import List

class DiscordFormatter:
    @staticmethod
    def split_message(text: str, max_length: int = 1900) -> List[str]:
        if len(text) <= max_length:
            return [text]

        chunks: List[str] = []
        lines = text.split("\n")
        current_chunk = ""

        for line in lines:
            if len(current_chunk) + len(line) + 1 <= max_length:
                current_chunk += line + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = line + "\n"

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks