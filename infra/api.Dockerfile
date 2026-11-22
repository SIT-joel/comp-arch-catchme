FROM node:22-alpine AS web-build
WORKDIR /app
COPY web/package.json web/package-lock.json* ./
RUN npm ci || npm install
COPY web/ .
RUN npm run build

FROM python:3.12-slim

WORKDIR /srv

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=web-build /app/dist ./web/dist

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
