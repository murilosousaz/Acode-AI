import fitz  # PyMuPDF
from typing import List

class PyMuPDFAdapter:
    @staticmethod
    def extract_text_from_pdf(file_path: str) -> str:
        doc = fitz.open(file_path)
        pages_text: List[str] = []

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text("text")

            cleaned_lines = [line.strip() for line in text.splitlines() if line.strip()]
            cleaned_page_text = "\n".join(cleaned_lines)

            if cleaned_page_text:
                pages_text.append(f"[Página {page_num + 1}]\n{cleaned_page_text}")

        doc.close()
        return "\n\n".join(pages_text)