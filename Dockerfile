FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY snmp_trap_receiver.py .
COPY .env* ./

# Copy MIB files
COPY MIB-C320/ ./MIB-C320/

# Expose SNMP trap port (default 162)
EXPOSE 162/udp

# Run as non-root user for security
RUN useradd -m -u 1000 snmpuser && \
    chown -R snmpuser:snmpuser /app

USER snmpuser

# Start the application
CMD ["python", "-u", "snmp_trap_receiver.py"]
