"""Registro central dos 3 modelos de slide. Cada entrada descreve tudo que o
parser (schema de campos), o LLM (schema JSON) e o renderer (nomes de shape)
precisam saber sobre aquele modelo especifico."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

TEMPLATES = {
    "petr": {
        "label": "Apresentação padrão",
        "file": BASE_DIR / "pptx_templates" / "PETR_modelo.pptx",
        "keeper_indices": [0, 1],  # capa + abertura, preservados como estao
        "content_template_index": 2,  # slide 53 'titulo + corpo', altura de caixa mediana entre 17 slides do mesmo tipo (Aula 01) (apos poda)
        "roles": {"titulo": "Google Shape;460;p49", "corpo": "Google Shape;461;p49"},
        "text_role_for_capacity": "corpo",
        "fields": ["titulo", "corpo"],  # campos de texto que o LLM deve preencher por item
        "image_roles": [],
    },
    "bb": {
        "label": "Mestre em Questões",
        "file": BASE_DIR / "pptx_templates" / "BB_modelo.pptx",
        "keeper_indices": [0, 1],
        "content_template_index": 2,  # slide 'questao/comentario', 1 bloco de texto (PETROBRAS MQ Bloco 3) (apos poda)
        "roles": {"corpo": "Retangulo 1"},  # sem acento neste arquivo
        "text_role_for_capacity": "corpo",
        "fields": ["corpo"],
        "image_roles": [],
    },
    "atualidades": {
        "label": "Atualidades",
        "file": BASE_DIR / "pptx_templates" / "Atualidades_modelo.pptx",
        "keeper_indices": [0, 1],
        "content_template_index": 2,  # slide 'noticia com categoria' (Atualidades Maio 2026) (ja era indice 2 antes da poda)
        "roles": {
            "categoria": "Retângulo: Cantos Arredondados 2",
            "manchete": "Retângulo 4",
            "resumo": "Retângulo 5",
            "imagem": "Picture 12",
        },
        "text_role_for_capacity": "resumo",
        "fields": ["categoria", "manchete", "resumo"],
        "image_roles": ["imagem"],
    },
}

UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

MAX_UPLOAD_MB = 50
ALLOWED_EXTENSIONS = {".docx", ".pdf"}
