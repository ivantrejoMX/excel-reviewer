FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Expose port
EXPOSE 8000

# Start server (no --reload in production)
CMD sh -c "python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"
