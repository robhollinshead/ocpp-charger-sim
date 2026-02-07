# Stage 1: Build frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Backend and serve frontend static
FROM python:3.11-slim
WORKDIR /app

# Copy backend
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/

# Copy frontend build for static serving
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Backend runs from backend/ so Python can resolve modules
WORKDIR /app/backend

ENV PORT=8001
ENV SERVE_STATIC=1
EXPOSE 8001

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
