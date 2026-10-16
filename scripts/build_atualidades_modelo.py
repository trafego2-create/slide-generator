"""Monta pptx_templates/Atualidades_modelo.pptx a partir do arquivo oficial do
time (ex: "Atualidades - V2.pptx"). O layout V2 tem uma etiqueta de categoria
diferente por categoria (cor e numero de bolinhas), entao o modelo guarda um
slide-fonte por categoria em vez de um so.

Mantem: capa, abertura e um slide-fonte de cada categoria (na ordem de
config.ATUALIDADES_CATEGORIAS). Remove as fotos de exemplo (o pipeline nao usa
imagens) e padroniza o nome da etiqueta de categoria em todos os slides-fonte,
ja que no arquivo original cada slide tem um nome diferente.

Roda: python scripts/build_atualidades_modelo.py "caminho/Atualidades - V2.pptx"
Os indices dos slides-fonte abaixo sao do arquivo V2 -- conferir se um arquivo
novo do time mudar a ordem dos slides."""
import copy
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from config import TEMPLATES, ATUALIDADES_CATEGORIAS
from prune_templates import keep_only_slides

KEEPER_INDICES = [0, 1]
# categoria -> indice do slide de exemplo no arquivo V2
SOURCE_SLIDES = {"BRASIL": 2, "GEOPOLÍTICA": 4, "GLOBALIZAÇÃO": 6, "DIVERSOS": 7}
CATEGORY_SHAPE_PREFIX = "Retângulo: Cantos Arredondados"


def _split_dots_and_label(paragraph):
    """Deixa a etiqueta com exatamente 2 runs: bolinhas e nome da categoria.
    No arquivo original a divisao varia (ex: 'bolinhas G' + 'LOBALIZAÇÃO', ou
    tudo num run so) -- o renderer troca so o ultimo run (ver
    slide_clone.set_label_text)."""
    runs = paragraph.runs
    full = "".join(r.text for r in runs)
    prefix = re.match(r"^[\s]*", full).group(0)
    if len(runs) == 1:
        runs[0]._r.addnext(copy.deepcopy(runs[0]._r))
        runs = paragraph.runs
    for middle in runs[1:-1]:
        middle._r.getparent().remove(middle._r)
    runs[0].text = prefix
    runs[-1].text = full[len(prefix):]


def main(source_path: str):
    cfg = TEMPLATES["atualidades"]
    assert list(SOURCE_SLIDES) == ATUALIDADES_CATEGORIAS

    prs = Presentation(source_path)
    keep_only_slides(prs, KEEPER_INDICES + list(SOURCE_SLIDES.values()))

    for slide in list(prs.slides)[len(KEEPER_INDICES):]:
        for shape in list(slide.shapes):
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                rid = shape._element.blipFill.blip.rEmbed
                shape._element.getparent().remove(shape._element)
                # sem isso a foto sai do slide mas continua dentro do arquivo
                slide.part.drop_rel(rid)
            elif shape.name.startswith(CATEGORY_SHAPE_PREFIX):
                shape.name = cfg["roles"]["categoria"]
                _split_dots_and_label(shape.text_frame.paragraphs[0])

    prs.save(str(cfg["file"]))
    size_mb = cfg["file"].stat().st_size / (1024 * 1024)
    print(f"{cfg['file']} ({size_mb:.1f}MB, {len(prs.slides)} slides)")


if __name__ == "__main__":
    main(sys.argv[1])
