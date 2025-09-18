FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bot.py .

# Create a non-root user
RUN useradd --create-home --shell /bin/bash botuser && \
    chown -R botuser:botuser /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R botuser:botuser /data

# Declare volume for persistent data
VOLUME /data

USER botuser

# Command to run the bot
CMD ["python", "bot.py"]