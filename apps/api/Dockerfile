# 3.13-slim, not 3.11 — requirements-lock.txt pins numpy==2.5.2 and
# scipy==1.18.1, both of which declare `Requires-Python >=3.12`. This base
# image must stay at or above the ML stack's minimum Python version (see
# requirements-lock.txt's own comment) or `pip install` fails to resolve
# them. 3.13 also matches the exact interpreter the lock file was verified
# against (355/355 tests passing).
FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# requirements-lock.txt (exact, verified versions) — NOT requirements.txt
# (loose ranges) — for a reproducible production image. See
# requirements-lock.txt's own header for how to regenerate it deliberately.
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
