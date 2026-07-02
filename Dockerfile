FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY bookbuddarr ./bookbuddarr

RUN pip install --no-cache-dir .

EXPOSE 8765 8788

CMD ["bookbuddarr", "torznab-serve", "--bind", "0.0.0.0", "--port", "8765"]
