"""Usa a OpenAI so pra DIVIDIR o material bruto do professor em itens (um item
= um slide-modelo preenchido). A IA nunca copia nem escreve o texto: recebe os
paragrafos numerados e devolve so onde cada item comeca (e se o primeiro
paragrafo do item e um titulo). O texto de cada item e montado aqui, direto
dos paragrafos originais -- por construcao, nenhum paragrafo some e nenhum e
reescrito (antes a IA copiava o texto e as vezes pulava topicos inteiros ou
trocava palavras, ex: 'Normal' virando 'Modo Normal')."""
import json
import re
import unicodedata

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL, TEMPLATES, ATUALIDADES_CATEGORIAS, ATUALIDADES_REGIOES
from parser import TableRow

_client = None


def _get_client():
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY nao configurada -- veja .env.example")
        # timeout curto por chamada -- sem isso, uma chamada travada podia
        # ficar pendurada pelo timeout default do SDK (bem mais longo) sem
        # nenhum sinal de erro nem progresso pro usuario
        _client = OpenAI(api_key=OPENAI_API_KEY, timeout=60.0, max_retries=2)
    return _client


def _schema(item_properties: dict) -> dict:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": item_properties,
                    "required": list(item_properties),
                    "additionalProperties": False,
                },
            },
        },
        "required": ["items"],
        "additionalProperties": False,
    }


_INICIO = {"type": "integer"}
_TEM_TITULO = {"type": "boolean"}

SCHEMAS = {
    "bb": {
        "name": "questoes_comentadas",
        "schema": _schema({"inicio": _INICIO}),
    },
    "petr": {
        "name": "conteudo_expositivo",
        "schema": _schema({"inicio": _INICIO, "tem_titulo": _TEM_TITULO}),
    },
    "atualidades": {
        "name": "noticias",
        "schema": _schema({
            "inicio": _INICIO,
            "tem_titulo": _TEM_TITULO,
            "categoria": {"type": "string", "enum": ATUALIDADES_CATEGORIAS},
            "regiao": {"type": "string", "enum": [""] + ATUALIDADES_REGIOES},
        }),
    },
}

MODEL_INSTRUCTIONS = {
    "bb": (
        "O material e um banco de questoes comentadas. Cada item e UMA unidade: "
        "uma questao (enunciado com alternativas) OU um comentario. Comece um "
        "item novo onde comeca cada questao (numeracao) e onde comeca cada "
        "comentario (normalmente iniciado por 'Comentario:'). Nunca deixe duas "
        "questoes ou dois comentarios no mesmo item, mesmo que sejam curtos."
    ),
    "petr": (
        "O material e uma aula expositiva. Comece um item novo em CADA titulo "
        "ou subtitulo do material -- linhas curtas que nomeiam um topico (ex: "
        "'Normal', 'Estrutura de Topicos', 'Iniciar a apresentacao') -- mesmo "
        "que o texto daquele topico seja bem curto. Nunca deixe dois topicos "
        "que tem titulo proprio no mesmo item. tem_titulo = true quando o "
        "paragrafo 'inicio' e esse titulo. Em trechos longos sem subtitulo, so "
        "comece item novo quando o assunto mudar claramente, com tem_titulo = "
        "false (o sistema ja divide texto longo em varios slides sozinho)."
    ),
    "atualidades": (
        "O material e um resumo de noticias. Cada item e uma noticia inteira. "
        "Normalmente o proprio material traz a categoria escrita numa linha "
        "antes da manchete (ex: 'BRASIL', 'GEOPOLÍTICA | Europa') -- nesse caso "
        "o item comeca nessa linha. Sem linha de categoria, o item comeca na "
        "manchete, com tem_titulo = true. Nunca junte noticias diferentes no "
        "mesmo item. So quando o material NAO trouxer a categoria escrita, "
        "escolha 'categoria' entre: BRASIL (o fato acontece no "
        "Brasil, mesmo que envolva empresa ou pais estrangeiro), GEOPOLÍTICA "
        "(fato de outro pais: governo, politica, lideres e figuras publicas, "
        "conflitos, relacoes entre paises), GLOBALIZAÇÃO (temas que atravessam "
        "fronteiras: economia/comercio global, crimes e redes internacionais, "
        "sociedade em escala global) ou DIVERSOS (o resto: ciencia, cultura, "
        "rankings, curiosidades). 'regiao' so pra GEOPOLÍTICA: o continente ou "
        "regiao principal da noticia; nas outras categorias, deixe vazio."
    ),
}

SYSTEM_PROMPT = """Voce divide material bruto de professor (texto extraido de docx/pdf) em \
itens, um item por slide. O material vem em paragrafos numerados: [0], [1], [2]... \
Voce NAO copia nem escreve o texto -- o sistema monta os slides com o texto \
original. Sua unica tarefa e indicar, pra cada item, o numero do paragrafo onde \
ele comeca ('inicio'). Cada item vai do seu 'inicio' ate o paragrafo anterior ao \
'inicio' do item seguinte, entao todo paragrafo pertence a exatamente um item. \
Liste os itens em ordem crescente de 'inicio', comecando pelo paragrafo [0]."""


# Tamanho maximo (em caracteres) de material bruto por chamada a OpenAI. A
# resposta agora e minuscula (so numeros), entao o limite e pela qualidade da
# leitura, nao mais pelo limite de tokens de saida.
MAX_BATCH_CHARS = 6000

def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


_CATEGORY_KEYS = {_strip_accents(c): c for c in ATUALIDADES_CATEGORIAS}
_CATEGORY_RE = re.compile(r"^(" + "|".join(_CATEGORY_KEYS) + r")\b\s*(?:[|–—:/-]\s*(.*))?$", re.IGNORECASE)
MAX_CATEGORY_LINE_CHARS = 60


def category_line(text: str) -> tuple[str, str] | None:
    """Se o paragrafo e a linha de categoria escrita no material (ex:
    'BRASIL', '• Geopolítica - Europa'), devolve (categoria, texto da
    etiqueta no formato do modelo, ex: 'GEOPOLÍTICA  |  Europa')."""
    clean = re.sub(r"^[^\w]+", "", text.replace("**", "")).strip()
    if not clean or len(clean) > MAX_CATEGORY_LINE_CHARS:
        return None
    match = _CATEGORY_RE.match(_strip_accents(clean))
    if not match:
        return None
    category = _CATEGORY_KEYS[match.group(1).upper()]
    # regiao como escrita no original (com acento), so a categoria em caixa alta
    region = clean[len(clean) - len(match.group(2)):].strip() if match.group(2) else ""
    return category, f"{category}  |  {region}" if region else category


# Um paragrafo marcado como titulo mais longo que isso, ou terminado em ponto
# (frase, nao titulo), e tratado como corpo -- protege a caixa de titulo de
# receber um paragrafo inteiro por engano da IA.
MAX_TITLE_CHARS = 150


def _looks_like_title(text: str) -> bool:
    return len(text) <= MAX_TITLE_CHARS and not text.replace("**", "").rstrip().endswith(".")


def _batch_end(paragraphs: list[str], start: int, max_chars: int = MAX_BATCH_CHARS) -> int:
    end = start
    total = 0
    while end < len(paragraphs) and (end == start or total + len(paragraphs[end]) <= max_chars):
        total += len(paragraphs[end])
        end += 1
    return end


def _segment_batch(model_key: str, paragraphs: list[str]) -> list[dict]:
    """Retorna os inicios de item do lote (indices locais), ordenados, sem
    repeticao, sempre comecando no 0."""
    client = _get_client()
    schema_cfg = SCHEMAS[model_key]

    numbered = "\n\n".join(f"[{i}] {p}" for i, p in enumerate(paragraphs))
    user_prompt = f"{MODEL_INSTRUCTIONS[model_key]}\n\nMaterial bruto do professor:\n\n{numbered}"

    response = client.chat.completions.create(
        model=TEMPLATES[model_key].get("openai_model", OPENAI_MODEL),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": schema_cfg["name"],
                "schema": schema_cfg["schema"],
                "strict": True,
            },
        },
    )

    data = json.loads(response.choices[0].message.content)

    starts = {}
    for item in data["items"]:
        idx = item["inicio"]
        # tabela fica inteira no item do topico dela -- nunca abre item numa linha de tabela
        if 0 <= idx < len(paragraphs) and idx not in starts and not isinstance(paragraphs[idx], TableRow):
            starts[idx] = item
    if TEMPLATES[model_key].get("category_slides"):
        # categoria escrita no material: toda linha de categoria abre uma
        # noticia, e a manchete logo abaixo dela nunca abre item separado
        for idx, text in enumerate(paragraphs):
            if category_line(text):
                starts.setdefault(idx, {"inicio": idx, "tem_titulo": True})
                starts.pop(idx + 1, None)
    if 0 not in starts:
        starts[0] = {"inicio": 0, "tem_titulo": False, "categoria": ""}
    return [starts[i] for i in sorted(starts)]


def segment_content(model_key: str, paragraphs: list[str], on_progress=None) -> list[tuple[int, int, dict]]:
    """Divide o material inteiro em segmentos (inicio, fim_exclusivo, meta da
    IA) que cobrem todos os paragrafos, em ordem, sem buraco nem sobreposicao.

    Material grande vai em varios lotes. O ultimo item de cada lote pode estar
    cortado no meio pelo limite do lote (ex: titulo no fim de um lote e o texto
    dele no comeco do seguinte), entao ele e descartado e o proximo lote
    recomeca no inicio dele -- assim um topico nunca fica partido entre lotes."""
    segments = []
    pos = 0
    batch_num = 0
    estimated_batches = max(1, -(-sum(len(p) for p in paragraphs) // MAX_BATCH_CHARS))
    while pos < len(paragraphs):
        batch_num += 1
        if on_progress:
            on_progress(batch_num, max(batch_num, estimated_batches))
        end = _batch_end(paragraphs, pos)
        starts = _segment_batch(model_key, paragraphs[pos:end])

        if end < len(paragraphs) and len(starts) > 1:
            region_end = pos + starts[-1]["inicio"]
            starts = starts[:-1]
        else:
            region_end = end

        bounds = [pos + s["inicio"] for s in starts] + [region_end]
        for s, seg_start, seg_end in zip(starts, bounds, bounds[1:]):
            segments.append((seg_start, seg_end, s))
        pos = region_end
    return segments


def structure_content(model_key: str, paragraphs: list[str], on_progress=None) -> list[dict]:
    """Retorna lista de dicts com as chaves de config.TEMPLATES[model_key]['fields'],
    com o texto copiado direto dos paragrafos originais. on_progress(lote_atual,
    total_estimado), se informado, e chamado antes de cada chamada a OpenAI."""
    cfg = TEMPLATES[model_key]
    title_field = cfg["title_field"]
    body_field = cfg["text_role_for_capacity"]

    items = []
    last_title = ""
    for start, end, meta in segment_content(model_key, paragraphs, on_progress):
        chunk = paragraphs[start:end]
        item = {field: meta.get(field, "") for field in cfg["fields"]}
        written_category = cfg.get("category_slides") and chunk and category_line(chunk[0])
        if written_category:
            # categoria vem do proprio material; a manchete e a linha seguinte
            item["categoria"] = written_category[1]
            chunk = chunk[1:]
            own_title = bool(chunk and _looks_like_title(chunk[0]))
        else:
            if meta.get("categoria") == "GEOPOLÍTICA" and meta.get("regiao"):
                # palpite da IA (material sem categoria escrita), no formato da etiqueta
                item["categoria"] = f"GEOPOLÍTICA  |  {meta['regiao']}"
            own_title = bool(title_field and meta.get("tem_titulo") and chunk and _looks_like_title(chunk[0]))
        if own_title:
            last_title = chunk[0]
            chunk = chunk[1:]
        if title_field:
            # item sem titulo proprio e continuacao do topico anterior
            item[title_field] = last_title
        item[body_field] = "\n".join(chunk)

        # a IA as vezes separa o titulo do texto logo abaixo dele, gerando um
        # slide so com titulo seguido de outro com o mesmo titulo herdado --
        # junta os dois num slide so
        if not own_title and items and title_field and not items[-1][body_field]:
            items[-1][body_field] = item[body_field]
            continue
        items.append(item)
    return items
