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
                            "titulo": {"type": "string"},
                            "corpo": {"type": "string"},
                        },
                        "required": ["titulo", "corpo"],
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
                            "categoria": {"type": "string"},
                            "manchete": {"type": "string"},
                            "resumo": {"type": "string"},
                        },
                        "required": ["categoria", "manchete", "resumo"],
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
        "O material e um banco de questoes comentadas. Os limites de cada "
        "unidade de conteudo ja estao marcados no proprio texto original "
        "(numeracao de questao, alternativas A a E, a palavra 'Comentario:' "
        "iniciando um comentario) -- identifique esses limites e crie UM "
        "item por unidade (um enunciado com alternativas, OU um comentario). "
        "Regra critica: NUNCA junte duas questoes ou comentarios diferentes "
        "no mesmo item, mesmo que juntos fiquem curtos -- cada questao e "
        "cada comentario, por menor que seja, e sempre o seu proprio item, "
        "nunca dividido nem fundido com outro. Um comentario normalmente "
        "comeca com 'Comentario:' no proprio texto original -- mantenha "
        "isso se ja estiver assim, nao adicione se nao estiver."
    ),
    "petr": (
        "O material e uma aula expositiva. Cada item tem 'titulo' (nome "
        "curto do conceito/topico, ex: 'ROM (Read-Only Memory)') e 'corpo' "
        "(a explicacao/definicao daquele conceito). Agrupe paragrafos "
        "relacionados ao MESMO conceito num so item, no campo 'corpo', ate "
        "aproximar de {budget} caracteres -- so abra um item novo quando o "
        "assunto/conceito mudar claramente ou esse tamanho for ultrapassado. "
        "NUNCA crie um item separado pra cada frase ou paragrafo curto "
        "isolado -- isso gera excesso de slides minusculos, o que e o erro "
        "mais comum aqui."
    ),
    "atualidades": (
        "O material e um resumo de noticias. Cada noticia distinta vira um "
        "item: 'categoria' e um rotulo curto em caixa alta pra area da "
        "noticia (ex: 'BRASIL', 'ECONOMIA', 'MUNDO'), 'manchete' e o titulo "
        "curto em caixa alta, 'resumo' sao os pontos principais DA MESMA "
        "noticia em frases curtas (cada frase um paragrafo, vira um bullet) "
        "-- agrupe todos os pontos de uma mesma noticia num so item, ate "
        "aproximar de {budget} caracteres no campo 'resumo'. NUNCA crie um "
        "item por frase isolada nem junte noticias diferentes no mesmo "
        "item; um item e sempre uma noticia inteira e so uma."
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


def _structure_batch(model_key: str, paragraphs: list[str], char_budget: int | None = None) -> list[dict]:
    client = _get_client()
    schema_cfg = SCHEMAS[model_key]

    raw_text = "\n\n".join(paragraphs)
    instructions = MODEL_INSTRUCTIONS[model_key].format(budget=char_budget or 900)

    user_prompt = f"{instructions}\n\nMaterial bruto do professor:\n\n{raw_text}"

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
    return data["items"]


def structure_content(
    model_key: str,
    paragraphs: list[str],
    char_budget: int | None = None,
    on_progress=None,
) -> list[dict]:
    """Retorna lista de dicts com as chaves esperadas por
    config.TEMPLATES[model_key]['fields'].

    Material grande e dividido em varios lotes (cada um uma chamada separada a
    OpenAI) pra nunca estourar o limite de tokens de saida de uma unica
    resposta -- essencial pro caso de uso real (lotes de 200 a 500 slides).
    char_budget (de renderer.get_capacity_budget) orienta a IA a agrupar
    conteudo ate o tamanho real de um slide, em vez de criar um item minusculo
    por frase -- sem isso, um material de 125 paginas pode virar milhares de
    itens fragmentados. on_progress(lote_atual, total_lotes), se informado, e
    chamado antes de cada chamada -- usado pra reportar status real ao
    usuario, nao so uma mensagem parada durante o tempo todo."""
    batches = _batch_paragraphs(paragraphs)
    all_items = []
    for i, batch in enumerate(batches, start=1):
        if on_progress:
            on_progress(i, len(batches))
        all_items.extend(_structure_batch(model_key, batch, char_budget))
    return all_items
