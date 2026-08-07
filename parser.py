"""Extrai texto bruto (paragrafos) de um docx ou pdf enviado pelo professor.
Nao interpreta nem estrutura o conteudo -- isso e trabalho do llm.py; aqui e
so extracao fiel do material bruto. Sem imagens por decisao de escopo atual."""
from pathlib import Path

import docx
import fitz  # pymupdf


def extract_docx(path: Path) -> list[str]:
    document = docx.Document(str(path))
    return [p.text.strip() for p in document.paragraphs if p.text.strip()]


def extract_pdf(path: Path) -> list[str]:
    doc = fitz.open(str(path))
    paragraphs = []
    for page in doc:
        text = page.get_text("text")
        for block in text.split("\n\n"):
            block = block.strip()
            if block:
                paragraphs.append(block)
    doc.close()
    return paragraphs


def extract(path: Path) -> list[str]:
    """Retorna a lista de paragrafos do documento."""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".pdf":
        return extract_pdf(path)
    raise ValueError(f"formato nao suportado: {suffix}")
