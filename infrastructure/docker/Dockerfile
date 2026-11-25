FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY apps/frontend/package.json apps/frontend/package-lock.json ./
RUN --mount=type=secret,id=claims_build_ca \
    if [ -f /run/secrets/claims_build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/claims_build_ca; fi; npm ci
COPY apps/frontend/ ./
RUN npm run build

FROM scratch AS application
WORKDIR /source
COPY apps/api/ ./apps/api/
COPY data/ ./data/
COPY data_engineering/ ./data_engineering/
COPY machine_learning/ ./machine_learning/
COPY generative_ai/ ./generative_ai/
COPY agentic_ai/ ./agentic_ai/
COPY mcp_server/ ./mcp_server/
COPY scripts/ ./scripts/
COPY --from=frontend /build/dist ./apps/frontend/dist/

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN --mount=type=secret,id=claims_build_ca \
    --mount=type=bind,from=application,source=/source,target=/source \
    set -e; \
    if [ -f /run/secrets/claims_build_ca ]; then export PIP_CERT=/run/secrets/claims_build_ca; fi; \
    pip install --no-cache-dir -r requirements.txt; \
    cp -a /source/. /app/; \
    mkdir -p apps/frontend/public artifacts; \
    useradd --create-home copilot; \
    chown -R copilot:copilot /app
USER copilot
ENV COPILOT_SERVE_UI=1 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-ec", "python -m scripts.export_demo && cp apps/frontend/public/demo.json apps/frontend/dist/demo.json && exec uvicorn apps.api.main:app --host 0.0.0.0 --port 8000"]
