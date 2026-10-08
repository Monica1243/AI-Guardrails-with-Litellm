FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system guardrails \
    && useradd --system \
    --gid guardrails \
    --create-home \
    guardrails

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_lg

COPY --chown=guardrails:guardrails . .

USER guardrails

EXPOSE 4000

CMD ["litellm", "--config", "/app/config.yml", "--port", "4000"]