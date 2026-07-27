"""Chama a OpenAI pra organizar o material bruto do professor nos campos do
modelo escolhido. Principio central (mesmo do briefing original): a IA NUNCA
reescreve ou parafraseia o conteudo do professor, so organiza/corta o texto
ja existente nos campos certos."""
import json

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL

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


SCHEMAS = {
    "bb": {
        "name": "questoes_comentadas",
        "schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"corpo": {"type": "string"}},
                        "required": ["corpo"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["items"],
            "additionalProperties": False,
        },
    },
    "petr": {
        "name": "conteudo_expositivo",
        "schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "corpo": {"type": "string"},
                            "imagem_indice": {"type": ["integer", "null"]},
                        },
                        "required": ["corpo", "imagem_indice"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["items"],
            "additionalProperties": False,
        },
    },
    "atualidades": {
        "name": "noticias",
        "schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "manchete": {"type": "string"},
                            "resumo": {"type": "string"},
                            "imagem_1_indice": {"type": ["integer", "null"]},
                            "imagem_2_indice": {"type": ["integer", "null"]},
                        },
                        "required": ["manchete", "resumo", "imagem_1_indice", "imagem_2_indice"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["items"],
            "additionalProperties": False,
        },
    },
}

MODEL_INSTRUCTIONS = {
    "bb": (
        "O material e um banco de questoes comentadas. Cada unidade de "
        "conteudo (um enunciado com alternativas, OU um comentario de "
        "resposta) vira um item separado no campo 'corpo'. Um comentario "
        "normalmente comeca com 'Comentario:' no proprio texto original -- "
        "mantenha isso se ja estiver assim, nao adicione se nao estiver."
    ),
    "petr": (
        "O material e uma aula expositiva. Cada bloco de conteudo com um "
        "tema proprio vira um item, com 'corpo' sendo o texto e "
        "'imagem_indice' apontando pra imagem de apoio mais relacionada "
        "(ou null se nenhuma imagem se aplica)."
    ),
    "atualidades": (
        "O material e um resumo de noticias. Cada noticia vira um item: "
        "'manchete' e o titulo curto em caixa alta, 'resumo' sao os pontos "
        "principais em frases curtas (cada frase um paragrafo, viram "
        "bullets), e os indices de imagem apontam pras fotos relacionadas "
        "aquela noticia especifica (ou null)."
    ),
}

SYSTEM_PROMPT = """Voce organiza material bruto de professor (texto extraido de docx/pdf) na \
estrutura de um modelo de slide. Regra mais importante, sem excecao: NUNCA \
reescreva, parafraseie, resuma ou corrija o conteudo do professor -- copie o \
texto original literalmente, so decidindo onde cortar e em qual campo/item \
colocar cada trecho. Se o material bruto nao tiver conteudo suficiente pra \
preencher um campo, deixe vazio ao inves de inventar."""


# Tamanho maximo (em caracteres) de material bruto por chamada a OpenAI. Um
# lote grande demais faz a resposta JSON estourar o limite de tokens de saida
# do modelo e vir cortada no meio (json.loads quebra com "Unterminated string").
# Mantendo lotes modestos, cada chamada fica bem dentro do limite mesmo com a
# saida sendo quase do mesmo tamanho da entrada (texto copiado verbatim).
MAX_BATCH_CHARS = 6000


def _batch_paragraphs(paragraphs: list[str], max_chars: int = MAX_BATCH_CHARS) -> list[list[str]]:
    batches = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        if current and current_len + len(para) > max_chars:
            batches.append(current)
            current = []
            current_len = 0
        current.append(para)
        current_len += len(para)
    if current:
        batches.append(current)
    return batches


def _structure_batch(model_key: str, paragraphs: list[str], images: list) -> list[dict]:
    client = _get_client()
    schema_cfg = SCHEMAS[model_key]

    raw_text = "\n\n".join(paragraphs)
    image_hint = ""
    if images:
        listing = "\n".join(f"[{i}] {p.name}" for i, p in enumerate(images))
        image_hint = (
            f"\n\nImagens disponiveis (use o indice no campo correspondente, "
            f"de 0 a {len(images) - 1}; nunca invente um indice fora desse intervalo):\n{listing}"
        )

    user_prompt = f"{MODEL_INSTRUCTIONS[model_key]}\n\nMaterial bruto do professor:\n\n{raw_text}{image_hint}"

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
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

    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise RuntimeError(
            "resposta da OpenAI cortada por limite de tokens mesmo apos dividir em lotes -- "
            "reduza MAX_BATCH_CHARS em llm.py"
        )

    data = json.loads(choice.message.content)

    resolved_items = []
    for item in data["items"]:
        resolved = {}
        for key, value in item.items():
            if key.endswith("_indice"):
                role = key[: -len("_indice")]
                resolved[role] = images[value] if value is not None and 0 <= value < len(images) else None
            else:
                resolved[key] = value
        resolved_items.append(resolved)

    return resolved_items


def structure_content(model_key: str, paragraphs: list[str], images: list, on_progress=None) -> list[dict]:
    """images: lista de Path das imagens extraidas do material bruto (na ordem
    em que apareceram). Retorna lista de dicts com as chaves ja resolvidas
    pros nomes de campo esperados por config.TEMPLATES[model_key]['fields'/'image_roles']
    (ex: 'imagem_indice' vira 'imagem': Path).

    Material grande e dividido em varios lotes (cada um uma chamada separada a
    OpenAI) pra nunca estourar o limite de tokens de saida de uma unica
    resposta -- essencial pro caso de uso real (lotes de 200 a 500 slides).
    on_progress(lote_atual, total_lotes), se informado, e chamado antes de cada
    chamada -- usado pra reportar status real ao usuario, nao so uma mensagem
    parada durante o tempo todo."""
    batches = _batch_paragraphs(paragraphs)
    all_items = []
    for i, batch in enumerate(batches, start=1):
        if on_progress:
            on_progress(i, len(batches))
        all_items.extend(_structure_batch(model_key, batch, images))
    return all_items
