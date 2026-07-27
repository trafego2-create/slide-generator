"""FastAPI + HTMX: upload de material bruto do professor, escolha do modelo,
acompanhamento assincrono do job e download do .pptx gerado."""
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import TEMPLATES, UPLOAD_DIR
import jobs

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Gerador de Slides")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"modelos": jobs.TEMPLATE_CHOICES}
    )


@app.post("/upload")
async def upload(
    request: Request,
    background_tasks: BackgroundTasks,
    arquivo: UploadFile = File(...),
    modelo: str = Form(...),
):
    if modelo not in TEMPLATES:
        raise HTTPException(400, f"modelo invalido: {modelo}")

    contents = await arquivo.read()
    try:
        jobs.validate_upload(arquivo.filename, len(contents))
    except ValueError as exc:
        return templates.TemplateResponse(
            request, "partials/erro.html", {"mensagem": str(exc)}
        )

    job_id = jobs.create_job(arquivo.filename, modelo)
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    upload_path = job_dir / arquivo.filename
    upload_path.write_bytes(contents)

    background_tasks.add_task(jobs.process_job, job_id, upload_path)

    return templates.TemplateResponse(
        request, "partials/status.html", {"job": jobs.get_job(job_id)}
    )


@app.get("/jobs/{job_id}")
def job_status(request: Request, job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job nao encontrado")
    return templates.TemplateResponse(request, "partials/status.html", {"job": job})


@app.get("/jobs/{job_id}/download")
def job_download(job_id: str):
    job = jobs.get_job(job_id)
    if job is None or job["status"] != "concluido" or not job["output_path"]:
        raise HTTPException(404, "arquivo ainda nao disponivel")
    return FileResponse(
        job["output_path"],
        filename=f"{job['model_key']}_{job['filename']}.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
