FROM python:3.10-slim

# 1. Install system dependencies (FFmpeg & tools for Node.js)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Node.js (Required by yt-dlp for signature extraction)
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 3. Create a non-root user for Hugging Face Spaces security
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    GRADIO_SERVER_NAME="0.0.0.0"

WORKDIR $HOME/app

# 4. Copy requirements first to leverage Docker cache
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the entire project
COPY --chown=user . .

# 6. Pre-create necessary directories with correct permissions
RUN mkdir -p Temp Output models/whispermodels models/mpmodels files logs fonts resources/prompts

# Hugging Face Spaces uses port 7860 by default
EXPOSE 7860

CMD ["python", "app.py"]