"""Mede quanto texto cabe numa caixa (shape) e divide texto longo em blocos que
respeitam o padrao visual. Importante: a simulacao de quebra de linha aqui e
usada SO pra estimar quantas linhas visuais um paragrafo vai ocupar (decidir
quando abrir um novo slide) -- os paragrafos originais nunca sao fragmentados
em varios paragrafos de saida, porque isso quebraria listas com marcador
(cada linha quebrada viraria um bullet solto). A quebra de linha em si fica
por conta do proprio PowerPoint ao renderizar."""
from pathlib import Path

from PIL import ImageFont

EMU_PER_INCH = 914400
DEFAULT_DPI = 96
LINE_SPACING = 1.2

# No Windows (dev local) usamos as fontes reais. No container Linux (deploy) elas
# nao existem -- Arial/Verdana sao proprietarias da Microsoft e nao vem no Linux
# base, entao usamos substitutos metricamente equivalentes so pra ESTIMAR quebra
# de linha (o .pptx gerado continua declarando Arial/Verdana de verdade; quem
# renderiza de fato e o PowerPoint do usuario, com a fonte real). Isso e uma
# aproximacao conhecida -- aceitavel porque o time de conteudo revisa depois.
_CANDIDATES = {
    "Arial": [
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "Verdana": [
        r"C:\Windows\Fonts\verdana.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ],
    "Calibri": [
        r"C:\Windows\Fonts\calibri.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
}


def _font_path(font_name):
    for path in _CANDIDATES.get(font_name, _CANDIDATES["Arial"]):
        if Path(path).exists():
            return path
    raise FileNotFoundError(
        f"nenhuma fonte disponivel pra estimar '{font_name}' -- "
        "instale fonts-liberation e fonts-dejavu-core (Linux) ou rode no Windows"
    )


def _wrap_paragraph(text, font, max_width_px):
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if font.getlength(trial) <= max_width_px or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _count_wrapped_lines(text, font, max_width_px):
    return len(_wrap_paragraph(text, font, max_width_px))


def max_lines_for_box(font_name, font_size_pt, box_height_emu, dpi=DEFAULT_DPI):
    font_px = round(font_size_pt * dpi / 72)
    line_height_px = font_px * LINE_SPACING
    box_height_px = box_height_emu / EMU_PER_INCH * dpi
    return max(1, int(box_height_px // line_height_px))


def split_text_to_slides(paragraphs, font_name, font_size_pt, box_width_emu, box_height_emu, dpi=DEFAULT_DPI):
    """paragraphs: lista de strings (cada uma um paragrafo/bullet do material bruto).
    Retorna lista de blocos de texto (um bloco = o que cabe em uma instancia do
    modelo). Cada bloco preserva os paragrafos originais intactos (join por "\\n"),
    nunca quebra uma frase/bullet ao meio -- exceto no caso raro de um unico
    paragrafo sozinho ja ser maior que a capacidade de um slide inteiro."""
    font_px = round(font_size_pt * dpi / 72)
    font = ImageFont.truetype(_font_path(font_name), font_px)
    box_width_px = box_width_emu / EMU_PER_INCH * dpi
    max_lines = max_lines_for_box(font_name, font_size_pt, box_height_emu, dpi)

    blocks = []
    current_paragraphs = []
    current_line_count = 0

    for para in paragraphs:
        para_line_count = _count_wrapped_lines(para, font, box_width_px)

        if current_line_count + para_line_count <= max_lines:
            current_paragraphs.append(para)
            current_line_count += para_line_count
        elif not current_paragraphs:
            # bloco vazio, mas o paragrafo sozinho e maior que a capacidade de um slide:
            # caso raro, precisa quebrar o proprio paragrafo em pedacos de texto corrido
            wrapped = _wrap_paragraph(para, font, box_width_px)
            for i in range(0, len(wrapped), max_lines):
                blocks.append([" ".join(wrapped[i:i + max_lines])])
            current_paragraphs = []
            current_line_count = 0
        else:
            blocks.append(current_paragraphs)
            if para_line_count <= max_lines:
                current_paragraphs = [para]
                current_line_count = para_line_count
            else:
                wrapped = _wrap_paragraph(para, font, box_width_px)
                for i in range(0, len(wrapped), max_lines):
                    blocks.append([" ".join(wrapped[i:i + max_lines])])
                current_paragraphs = []
                current_line_count = 0

    if current_paragraphs:
        blocks.append(current_paragraphs)

    return ["\n".join(block) for block in blocks], max_lines
