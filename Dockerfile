FROM python:3.12-slim

# fonts-liberation (clone metrico do Arial) e fonts-dejavu-core (aproximacao do
# Verdana) sao usadas so pra ESTIMAR quebra de linha ao decidir quando dividir
# conteudo em mais slides -- o .pptx gerado continua com Arial/Verdana de
# verdade, renderizadas pelo PowerPoint do usuario final.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads output

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
