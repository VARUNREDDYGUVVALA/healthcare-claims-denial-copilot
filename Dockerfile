FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=claims_build_ca \
    if [ -f /run/secrets/claims_build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/claims_build_ca; fi; npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN --mount=type=secret,id=claims_build_ca \
    if [ -f /run/secrets/claims_build_ca ]; then export PIP_CERT=/run/secrets/claims_build_ca; fi; pip install --no-cache-dir -r requirements.txt
COPY copilot/ ./copilot/
COPY --from=frontend /build/dist ./frontend/dist/
RUN mkdir -p frontend/public artifacts && useradd --create-home copilot && chown -R copilot:copilot /app
USER copilot
ENV COPILOT_SERVE_UI=1 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-ec", "python -m copilot.pipeline && cp frontend/public/demo.json frontend/dist/demo.json && exec uvicorn copilot.api:app --host 0.0.0.0 --port 8000"]
