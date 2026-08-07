"""Extrai texto bruto (paragrafos) de um docx ou pdf enviado pelo professor.
Nao interpreta nem estrutura o conteudo -- isso e trabalho do llm.py; aqui e
so extracao fiel do material bruto. Sem imagens por decisao de escopo atual.

Trechos em negrito no original sao marcados com **texto** (estilo markdown)
pra sobreviver a passagem pela IA e serem reaplicados na renderizacao (ver
slide_clone.set_text_preserving_format)."""
import re
from pathlib import Path

import docx
import fitz  # pymupdf


def _merge_bold_segments(runs_or_spans):
    """runs_or_spans: lista de (texto, bold). Funde vizinhos com o mesmo
    estado de negrito, pra nao gerar marcadores **encostados** feios."""
    segments = []
    for text, bold in runs_or_spans:
        if not text:
            continue
        if segments and segments[-1][1] == bold:
            segments[-1] = (segments[-1][0] + text, bold)
        else:
            segments.append((text, bold))
    return segments


def _mark_bold(segments) -> str:
    return "".join(f"**{text}**" if bold else text for text, bold in segments)


def extract_docx(path: Path) -> list[str]:
    document = docx.Document(str(path))
    paragraphs = []
    for p in document.paragraphs:
        segments = _merge_bold_segments([(r.text, bool(r.bold)) for r in p.runs])
        text = _mark_bold(segments).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def extract_pdf(path: Path) -> list[str]:
    doc = fitz.open(str(path))
    paragraphs = []
    for page in doc:
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:  # 0 = bloco de texto
                continue
            raw_segments = []
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text:
                        continue
                    is_bold = bool(span.get("flags", 0) & 16) or "bold" in span.get("font", "").lower()
                    raw_segments.append((text, is_bold))
                raw_segments.append((" ", False))
            block_text = _mark_bold(_merge_bold_segments(raw_segments)).strip()
            if block_text:
                paragraphs.append(re.sub(r" {2,}", " ", block_text))
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
