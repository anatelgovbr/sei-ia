# Observabilidade

> Langfuse + OpenTelemetry

## Langfuse

Plataforma de observabilidade para LLMs.

**Arquivo**: `sei_ia/configs/langfuse_config.py`

### Configuração

```bash
ASSISTENTE_USE_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
LANGFUSE_URL=http://langfuse:3005
```

### Funcionalidades

- Trace de chamadas LLM
- Métricas de latência e tokens
- Feedback de usuários
- Dashboard de análise

## OpenTelemetry

Instrumentação para métricas e traces.

### Configuração

```bash
ENABLE_OTEL_METRICS=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
```

### Instrumentação

- FastAPI requests
- HTTP calls
- SQLAlchemy queries
- Logging

### Instalação

```bash
uv sync --extra otel
```

### Execução

```bash
uv run opentelemetry-instrument gunicorn sei_ia.main:app -c sei_ia/configs/gunicorn_conf.py
```

## Middlewares

| Middleware | Função |
|------------|--------|
| TraceMiddleware | Adiciona trace_id |
| MetricsMeddleware | Coleta métricas OTEL |
| RequestMiddleware | Log de requisições |
