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
from docx.table import Table
from docx.text.hyperlink import Hyperlink


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


class TableRow(str):
    """Paragrafo que veio de uma linha de tabela. Continua sendo uma str
    normal; o llm.py usa o tipo pra nunca comecar um slide no meio de uma
    tabela (sem isso a IA tratava cada linha como um item separado)."""


def _mark_bold(segments) -> str:
    return "".join(f"**{text}**" if bold else text for text, bold in segments)


def _docx_paragraph_text(p) -> str:
    """Texto do paragrafo incluindo trechos dentro de hyperlink (p.runs sozinho
    ignora esses trechos e o texto saia com buraco)."""
    runs = []
    for content in p.iter_inner_content():
        if isinstance(content, Hyperlink):
            runs.extend(content.runs)
        else:
            runs.append(content)
    return _mark_bold(_merge_bold_segments([(r.text, bool(r.bold)) for r in runs])).strip()


def _docx_table_rows(table) -> list[str]:
    """Cada linha da tabela vira um paragrafo com as celulas separadas por ' | '.
    O modelo de slide nao tem tabela, entao o conteudo entra como texto (antes
    tabelas eram ignoradas e sumiam do resultado, ex: tabela de atalhos)."""
    rows = []
    for row in table.rows:
        cells = []
        seen = set()
        for cell in row.cells:
            # celula mesclada aparece repetida em row.cells
            if id(cell._tc) in seen:
                continue
            seen.add(id(cell._tc))
            text = " ".join(t for t in (_docx_paragraph_text(p) for p in cell.paragraphs) if t)
            if text:
                cells.append(text)
        if cells:
            rows.append(TableRow(" | ".join(cells)))
    return rows


def extract_docx(path: Path) -> list[str]:
    document = docx.Document(str(path))
    paragraphs = []
    # paragrafos e tabelas na ordem em que aparecem no documento
    for block in document.iter_inner_content():
        if isinstance(block, Table):
            paragraphs.extend(_docx_table_rows(block))
        else:
            text = _docx_paragraph_text(block)
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
