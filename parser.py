"""Extrai texto bruto (paragrafos) e imagens embutidas de um docx ou pdf
enviado pelo professor. Nao interpreta nem estrutura o conteudo -- isso e
trabalho do llm.py; aqui e so extracao fiel do material bruto."""
from pathlib import Path

import docx
import fitz  # pymupdf


def extract_docx(path: Path, images_dir: Path):
    document = docx.Document(str(path))

    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]

    images_dir.mkdir(parents=True, exist_ok=True)
    image_paths = []
    for i, rel in enumerate(document.part.rels.values()):
        if "image" in rel.reltype:
            ext = rel.target_ref.split(".")[-1]
            out_path = images_dir / f"img_{i:03d}.{ext}"
            out_path.write_bytes(rel.target_part.blob)
            image_paths.append(out_path)

    return paragraphs, image_paths


def extract_pdf(path: Path, images_dir: Path):
    doc = fitz.open(str(path))

    paragraphs = []
    for page in doc:
        text = page.get_text("text")
        for block in text.split("\n\n"):
            block = block.strip()
            if block:
                paragraphs.append(block)

    images_dir.mkdir(parents=True, exist_ok=True)
    image_paths = []
    seen_xrefs = set()
    counter = 0
    for page in doc:
        for img in page.get_images(full=True):
            xref = img[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            base_image = doc.extract_image(xref)
            ext = base_image["ext"]
            out_path = images_dir / f"img_{counter:03d}.{ext}"
            out_path.write_bytes(base_image["image"])
            image_paths.append(out_path)
            counter += 1

    doc.close()
    return paragraphs, image_paths


def extract(path: Path, images_dir: Path):
    """Retorna (paragrafos: list[str], imagens: list[Path])."""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_docx(path, images_dir)
    if suffix == ".pdf":
        return extract_pdf(path, images_dir)
    raise ValueError(f"formato nao suportado: {suffix}")
