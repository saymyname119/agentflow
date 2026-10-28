FROM node:22-slim AS console
WORKDIR /src
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm ci --no-audit --no-fund
COPY frontend ./frontend
COPY evaluation ./evaluation
RUN cd frontend && npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY approvalflow ./approvalflow
COPY --from=console /src/frontend/dist ./approvalflow/web
RUN pip install --no-cache-dir . && useradd --create-home app && mkdir /app/.demo && chown app /app/.demo
COPY policy.json ./
USER app
EXPOSE 8000
CMD ["approvalflow", "serve"]
