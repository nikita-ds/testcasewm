FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python deps (kept separate for better layer caching)
COPY 02_dialogs_generation/requirements.txt /app/02_dialogs_generation/requirements.txt
RUN pip install --no-cache-dir -r /app/02_dialogs_generation/requirements.txt

# Copy repo (needed for prompts + scripts + to access 01_data_generation artifacts if not bind-mounted)
COPY . /app

WORKDIR /app/02_dialogs_generation

# Default to showing help; actual commands are provided via docker compose run
CMD ["python", "generate_dialogs.py", "--help"]
