FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OLLAMA_URL=http://host.docker.internal:11434

WORKDIR /app

# System dependencies
# ffmpeg      — required by ASR engine to convert webm→wav
# portaudio   — required by sounddevice/pyaudio (import-time, not runtime in Docker)
# build-essential — needed to compile some pip packages
RUN apt-get update --fix-missing && apt-get install -y --fix-missing \
    build-essential \
    portaudio19-dev \
    libportaudio2 \
    ffmpeg \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip

# Install sounddevice/pyaudio separately with fallback
# (they may warn about no audio device in Docker — that's OK,
#  the voice pipeline never calls record_audio() or play_audio() directly)
RUN pip install --no-cache-dir sounddevice pyaudio || true

# Install everything else
RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    "uvicorn[standard]==0.30.6" \
    websockets==12.0 \
    requests==2.32.3 \
    psutil==6.0.0 \
    python-multipart==0.0.12 \
    faster-whisper \
    onnxruntime \
    piper-tts \
    scipy \
    numpy

# Copy application code
COPY . .

# voices/ directory must exist and contain:
#   en_US-lessac-medium.onnx
#   en_US-lessac-medium.onnx.json
# See README for download instructions.
RUN mkdir -p voices

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
