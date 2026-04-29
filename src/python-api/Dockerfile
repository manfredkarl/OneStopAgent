FROM python:3.13-slim

WORKDIR /app

# Install Node.js for PptxGenJS slide generation
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Node deps (pptxgenjs for slide generation)
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev 2>/dev/null || npm install --omit=dev

# App code
COPY . .

# Create output directory for generated PPTX files
RUN mkdir -p output

EXPOSE 8000

# Single worker — required because we use in-memory ProjectStore.
# Multiple workers each have their own Python process and independent state,
# which would cause 'project not found' errors across requests.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
