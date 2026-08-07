"""Orquestra o pipeline completo (parser -> LLM -> renderer) em background e
mantem o status de cada job. Armazenamento em memoria (dict) -- suficiente pra
ferramenta interna de baixo volume rodando num unico worker; se um dia precisar
escalar pra mais de um worker/processo, trocar por Redis ou banco."""
import shutil
import traceback
import uuid
from pathlib import Path

from config import TEMPLATES, UPLOAD_DIR, ALLOWED_EXTENSIONS, MAX_UPLOAD_MB
import parser as doc_parser
import llm
import renderer

JOBS: dict[str, dict] = {}


def create_job(filename: str, model_key: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "id": job_id,
        "filename": filename,
        "model_key": model_key,
        "status": "pendente",
        "erro": None,
        "output_path": None,
    }
    return job_id


def get_job(job_id: str) -> dict | None:
    return JOBS.get(job_id)


def validate_upload(filename: str, size_bytes: int):
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"formato nao suportado: {suffix} (use .docx ou .pdf)")
    if size_bytes > MAX_UPLOAD_MB * 1024 * 1024:
        raise ValueError(f"arquivo maior que {MAX_UPLOAD_MB}MB")


def process_job(job_id: str, upload_path: Path):
    job = JOBS[job_id]
    model_key = job["model_key"]

    try:
        job["status"] = "extraindo texto"
        paragraphs = doc_parser.extract(upload_path)

        char_budget = renderer.get_capacity_budget(model_key)

        def report_progress(batch_num, total_batches):
            job["status"] = f"estruturando conteudo (IA) -- lote {batch_num} de {total_batches}"

        job["status"] = "estruturando conteudo (IA)"
        items = llm.structure_content(
            model_key, paragraphs, char_budget=char_budget, on_progress=report_progress
        )

        job["status"] = "gerando pptx"
        out_path = renderer.build_presentation(model_key, items, job_id=job_id)

        job["output_path"] = out_path
        job["status"] = "concluido"
    except Exception as exc:
        job["status"] = "erro"
        job["erro"] = str(exc)
        traceback.print_exc()
    finally:
        # limpa o material bruto enviado (mantem so o pptx gerado em output/)
        shutil.rmtree(UPLOAD_DIR / job_id, ignore_errors=True)


TEMPLATE_CHOICES = [(key, cfg["label"]) for key, cfg in TEMPLATES.items()]
