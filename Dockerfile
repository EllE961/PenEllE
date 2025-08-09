# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY . .

# Make sure scripts in /root/.local are callable
ENV PATH=/root/.local/bin:$PATH

# Create non-root user
RUN useradd -m -u 1000 penelle && chown -R penelle:penelle /app
USER penelle

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "src.web.app:app", "--host", "0.0.0.0", "--port", "8000"]