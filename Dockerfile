FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TIKTOKEN_CACHE_DIR=/app/.tiktoken \
    OUTPUT_DIR=/app/out

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

COPY helpcenter_sync/ helpcenter_sync/
COPY main.py .

RUN useradd --create-home app && mkdir -p /app/out && chown app /app/out
USER app

ENTRYPOINT ["python"]
CMD ["main.py"]
