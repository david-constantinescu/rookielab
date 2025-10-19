# Use Nixpacks as the base image
FROM ghcr.io/railwayapp/nixpacks:ubuntu-1731369831

# Set the working directory
WORKDIR /app

# Install Python, pip, and poppler-utils
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    poppler-utils && \
    apt-get clean

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose Flask port
EXPOSE 2014

# Start the Flask app
CMD ["python3", "app.py"]