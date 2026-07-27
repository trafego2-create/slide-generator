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
        "content_template_index": 4,  # slide 'texto + imagem', fonte do clone
        "roles": {"corpo": "Rectangle 3", "imagem": "Picture 2"},
        "text_role_for_capacity": "corpo",
        "fields": ["corpo"],  # campos de texto que o LLM deve preencher por item
        "has_image": True,
        "image_roles": ["imagem"],
    },
    "bb": {
        "label": "Mestre em Questões",
        "file": BASE_DIR / "pptx_templates" / "BB_modelo.pptx",
        "keeper_indices": [0, 1],
        "content_template_index": 3,  # slide 'questao/comentario', 1 bloco de texto, sem imagem
        "roles": {"corpo": "Retângulo 1"},
        "text_role_for_capacity": "corpo",
        "fields": ["corpo"],
        "has_image": False,
        "image_roles": [],
    },
    "atualidades": {
        "label": "Atualidades",
        "file": BASE_DIR / "pptx_templates" / "Atualidades_modelo.pptx",
        "keeper_indices": [0, 1],
        "content_template_index": 3,  # slide 'noticia padrao' (manchete+resumo+2 imagens, sem categoria)
        "roles": {
            "manchete": "Retângulo 4",
            "resumo": "Retângulo 5",
            "imagem_1": "Imagem 1",
            "imagem_2": "Picture 2",
        },
        "text_role_for_capacity": "resumo",
        "fields": ["manchete", "resumo"],
        "has_image": True,
        "image_roles": ["imagem_1", "imagem_2"],
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
