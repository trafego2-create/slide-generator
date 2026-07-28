"""Monta o .pptx final: clona o slide-modelo do arquivo real uma vez por item,
preenche texto/imagem pelos papeis definidos em config.TEMPLATES, e no final
remove todo slide original que nao seja capa/abertura (keeper_indices)."""
import sys
import uuid
from pathlib import Path

from pptx import Presentation
from pptx.oxml.ns import qn

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from slide_clone import duplicate_slide, find_shape_by_name, set_text_preserving_format, replace_picture  # noqa: E402
from text_fit import split_text_to_slides, estimate_char_budget  # noqa: E402

from config import TEMPLATES, OUTPUT_DIR


def _get_capacity_params(cfg):
    """(font_name, font_size_pt, box_width_emu, box_height_emu) do shape que
    define a capacidade de texto do modelo -- usado tanto pra dividir itens
    grandes demais quanto pra estimar o orcamento de caracteres por item."""
    role = cfg["text_role_for_capacity"]
    shape_name = cfg["roles"][role]

    prs = Presentation(str(cfg["file"]))
    template_slide = prs.slides[cfg["content_template_index"]]
    template_shape = find_shape_by_name(template_slide, shape_name)
    run = template_shape.text_frame.paragraphs[0].runs[0]
    font_name = run.font.name or "Arial"
    # quando 'sz' nao aparece em run/paragrafo/lstStyle, o padrao implicito da spec OOXML e 18pt
    font_size_pt = run.font.size.pt if run.font.size else 18.0
    return font_name, font_size_pt, template_shape.width, template_shape.height


def get_capacity_budget(model_key: str) -> int:
    """Estimativa de quantos caracteres cabem no campo principal de texto do
    modelo -- usado so como orientacao pro LLM agrupar conteudo num tamanho
    de item razoavel, evitando um item minusculo por frase."""
    cfg = TEMPLATES[model_key]
    font_name, font_size_pt, box_w, box_h = _get_capacity_params(cfg)
    return estimate_char_budget(font_name, font_size_pt, box_w, box_h)


def expand_items_by_capacity(cfg, items):
    """Para o campo marcado como 'text_role_for_capacity', divide o item em
    varios (um por slide) quando o texto nao cabe no padrao. Os demais campos
    do item sao repetidos em todos os slides gerados a partir dele (ex: a
    mesma foto acompanha todos os pedacos de uma noticia longa)."""
    role = cfg["text_role_for_capacity"]
    font_name, font_size_pt, box_w, box_h = _get_capacity_params(cfg)

    expanded = []
    for item in items:
        text = item.get(role, "") or ""
        paragraphs = [p for p in text.split("\n") if p.strip()]
        if not paragraphs:
            expanded.append(item)
            continue
        blocks, _ = split_text_to_slides(paragraphs, font_name, font_size_pt, box_w, box_h)
        for block in blocks:
            new_item = dict(item)
            new_item[role] = block
            expanded.append(new_item)

    return expanded


def _remove_non_keeper_originals(prs, original_count, keeper_indices):
    xml_slides = prs.slides._sldIdLst
    slide_elements = list(xml_slides)
    keep = set(keeper_indices)
    for i in range(original_count):
        if i in keep:
            continue
        el = slide_elements[i]
        rid = el.get(qn("r:id"))
        xml_slides.remove(el)
        prs.part.drop_rel(rid)


def build_presentation(model_key: str, items: list[dict], job_id: str | None = None) -> Path:
    """items: lista de dicts com os campos de texto (cfg['fields']) e,
    quando aplicavel, os caminhos de imagem por papel (cfg['image_roles'])."""
    cfg = TEMPLATES[model_key]

    expanded_items = expand_items_by_capacity(cfg, items)

    prs = Presentation(str(cfg["file"]))
    original_count = len(prs.slides._sldIdLst)

    for item in expanded_items:
        new_slide = duplicate_slide(prs, cfg["content_template_index"])

        for field in cfg["fields"]:
            shape = find_shape_by_name(new_slide, cfg["roles"][field])
            set_text_preserving_format(shape, item.get(field, "") or "")

        for image_role in cfg["image_roles"]:
            image_path = item.get(image_role)
            if image_path:
                shape = find_shape_by_name(new_slide, cfg["roles"][image_role])
                replace_picture(shape, str(image_path))

    _remove_non_keeper_originals(prs, original_count, cfg["keeper_indices"])

    job_id = job_id or uuid.uuid4().hex[:8]
    out_path = OUTPUT_DIR / f"{model_key}_{job_id}.pptx"
    prs.save(str(out_path))
    return out_path
