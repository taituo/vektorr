# Vektorr Brain Service
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Environment
ENV PYTHONUNBUFFERED=1
ENV BRAIN_DECISIONS_LOG_PATH=/app/data/decisions.jsonl
ENV BRAIN_MANUAL_LOG_PATH=/app/data/manual_trades.jsonl

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run
CMD ["uvicorn", "brain.service:app", "--host", "0.0.0.0", "--port", "8000"]
