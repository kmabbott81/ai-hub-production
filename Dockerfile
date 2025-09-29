FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose the port Railway will use
EXPOSE $PORT

# Create a script to run streamlit with dynamic port
RUN echo '#!/bin/bash\nstreamlit run app.py --server.address=0.0.0.0 --server.port=$PORT --server.headless=true' > start.sh
RUN chmod +x start.sh

# Run the application
CMD ["./start.sh"]