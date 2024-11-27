FROM python:3.11-slim
ENV DOCKER_ENV=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies including FFmpeg and git
RUN apt-get update && \
    apt-get install -y ffmpeg git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install -r requirements.txt

# Install latest yt-dlp
RUN pip install -U yt-dlp

# Copy the rest of the application
COPY . .

# Make start script executable
RUN chmod +x start.sh

# Command to run the application
CMD ["./start.sh"]