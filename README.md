# SNMP Trap to Kafka Service

Python application that receives SNMP traps from ZTE C320 OLT and forwards them to Apache Kafka with intelligent ONT registration detection.

## Features

- **SNMP Trap Receiver**: Listens for SNMPv2c traps on UDP port 162
- **Kafka Publisher**: Forwards parsed trap data to Kafka topics
- **MIB Support**: Includes ZTE C320 OLT + LibreNMS MIBs (230,000+ OIDs)
- **Manufacturer Detection**: Automatically identifies device manufacturer from enterprise OIDs
- **ONT Registration Detection**: Automatically detects and decodes ONT registration events
- **Dual Kafka Topics**: 
  - General traps → `olt_snmp_traps`
  - ONT registrations → `olt_ont_registration`
- **Docker Ready**: Runs as a containerized service
- **Logging**: Comprehensive logging for debugging and monitoring

## Prerequisites

- Docker and Docker Compose
- ZTE C320 OLT configured to send traps
- Kafka broker accessible (default: 10.42.4.19:9092)

## Quick Start

### 1. Build MIB Database

First, build the MIB database from ZTE C320 MIB files:

```bash
# Make the script executable
chmod +x build_mib_db.sh

# Build the database
./build_mib_db.sh
```

This will create `mib_database.db` containing all OID mappings from the ZTE C320 MIBs.

**Optional: Query the MIB database**

```bash
# Show statistics
python3 query_mib.py stats

# Look up an OID
python3 query_mib.py oid 1.3.6.1.4.1.3902

# Search by name
python3 query_mib.py name gpon

# List all traps
python3 query_mib.py traps
```

### 2. Configure Environment

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` with your settings:
```bash
# SNMP Configuration
SNMP_LISTEN_HOST=0.0.0.0
SNMP_LISTEN_PORT=162
SNMP_COMMUNITY=wg1Community

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=10.42.4.19:9092
KAFKA_TOPIC=olt_snmp_traps
KAFKA_REGISTRATION_TOPIC=olt_ont_registration

# Logging
LOG_LEVEL=INFO
```

### 3. Build and Run with Docker Compose

```bash
# Build the Docker image
docker-compose build

# Start the service
docker-compose up -d

# View logs
docker-compose logs -f
```

### 4. Configure ZTE C320 OLT

On your ZTE C320 OLT, configure SNMP trap destination:

```
snmp-server host 10.42.4.3 version 2c wg1Community enable notifications target-addr-name kafka
```

Where `10.42.4.3` is the IP address of the server running this application.

## Manual Installation (Without Docker)

### 1. Build MIB Database

```bash
./build_mib_db.sh
```

### 2. Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. Run the Application

```bash
# Make sure .env is configured
python snmp_trap_receiver.py
```

**Note**: Running on port 162 requires root/sudo privileges:
```bash
sudo python snmp_trap_receiver.py
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SNMP_LISTEN_HOST` | `0.0.0.0` | SNMP trap receiver bind address |
| `SNMP_LISTEN_PORT` | `162` | SNMP trap receiver port (UDP) |
| `SNMP_COMMUNITY` | `wg1Community` | SNMPv2c community string |
| `KAFKA_BOOTSTRAP_SERVERS` | `10.42.4.19:9092` | Kafka broker addresses (comma-separated) |
| `KAFKA_TOPIC` | `olt_snmp_traps` | Kafka topic for general trap messages |
| `KAFKA_REGISTRATION_TOPIC` | `olt_ont_registration` | Kafka topic for ONT registration events |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Kafka Message Format

#### General Trap Messages (Topic: `olt_snmp_traps`)

All traps are published to Kafka in JSON format with MIB information:

```json
{
  "timestamp": "2025-11-03T03:07:18.805Z",
  "source_ip": "10.42.3.24",
  "source_port": 161,
  "trap_oid": "1.3.6.1.4.1.3902.1082.500.10.3.1.80",
  "is_registration": true,
  "trap_info": {
    "name": "zxGponOntRegisterTrap",
    "description": "ONT registration event notification",
    "module": "ZXGPON-ONTMGMT-MIB"
  },
  "registration_data": {
    "event_type": "ont_registration",
    "ont_model": "MH80",
    "ont_serial": "MHAR08DF4BD9",
    "vendor_id": "MHAR",
    "device_serial": "08DF4BD9",
    "ont_firmware": "XPONV4.2.2M16",
    "registration_time": "2025-11-03 11:07:17",
    "ont_index": "285278466",
    "ont_password": "0x00000000000000000000"
  },
  "trap_data": {
    "1.3.6.1.2.1.1.3.0": {
      "oid": "1.3.6.1.2.1.1.3.0",
      "name": "sysUpTime",
      "value": "102551400",
      "type": "TimeTicks",
      "syntax": "TimeTicks",
      "description": "The time since the network management..."
    }
  }
}
```

#### ONT Registration Messages (Topic: `olt_ont_registration`)

When an ONT registration is detected, a simplified message is sent to the registration topic:

```json
{
  "timestamp": "2025-11-03T03:07:18.805Z",
  "source_ip": "10.42.3.24",
  "event_type": "ont_registration",
  "trap_oid": "1.3.6.1.4.1.3902.1082.500.10.3.1.80",
  "ont_data": {
    "event_type": "ont_registration",
    "ont_model": "MH80",
    "ont_serial": "MHAR08DF4BD9",
    "vendor_id": "MHAR",
    "device_serial": "08DF4BD9",
    "ont_firmware": "XPONV4.2.2M16",
    "registration_time": "2025-11-03 11:07:17",
    "ont_index": "285278466"
  }
}
```

**Key Features:**
- **Automatic Detection**: Identifies ONT registration traps by OID pattern
- **Decoded Data**: Serial numbers, timestamps, and firmware versions decoded from hex
- **Dual Publishing**: Full trap to general topic, simplified registration to dedicated topic
- **MIB Lookups**: Each OID includes its human-readable name
- **Descriptions**: Parameter descriptions from MIB files
- **Table Indices**: Automatic detection of table entry indices
- **Manufacturer Detection**: Automatic identification of device manufacturer from OID

### Manufacturer Detection

The application automatically identifies device manufacturers from enterprise OIDs:

```json
{
  "timestamp": "2025-11-03T03:07:18.805Z",
  "source_ip": "10.42.3.24",
  "trap_oid": "1.3.6.1.4.1.3902.1082.500.10.3.1.80",
  "manufacturer": "ZTE Corporation",
  "enterprise_id": "3902",
  "is_enterprise_trap": true,
  "is_standard_trap": false,
  "trap_data": {
    "1.3.6.1.2.1.2.2.1.7.285278467": {
      "oid": "1.3.6.1.2.1.2.2.1.7.285278467",
      "manufacturer": "IETF Standard MIB",
      "is_enterprise": false,
      "is_standard": true,
      ...
    }
  }
}
```

**Supported Manufacturers:**
- ZTE Corporation (3902)
- Cisco Systems (9)
- Huawei Technologies (2011)
- Juniper Networks (2636)
- Ubiquiti Networks (10002)
- And 25+ more vendors

**Test manufacturer lookup:**
```bash
python3 test_manufacturer_lookup.py
```

## Docker Management

### View Logs
```bash
docker-compose logs -f snmp-to-kafka
```

### Restart Service
```bash
docker-compose restart
```

### Stop Service
```bash
docker-compose down
```

### Rebuild After Changes
```bash
docker-compose down
docker-compose build
docker-compose up -d
```

## Troubleshooting

### Port 162 Permission Denied

Port 162 requires elevated privileges. Solutions:

1. **Using Docker** (Recommended): Docker handles privileges automatically
2. **Manual run**: Use `sudo` or configure capabilities:
   ```bash
   sudo setcap cap_net_bind_service=+ep $(which python3)
   ```

### Not Receiving Traps

1. **Check firewall**:
   ```bash
   sudo ufw allow 162/udp
   ```

2. **Verify service is listening**:
   ```bash
   sudo netstat -ulnp | grep 162
   ```

3. **Test with snmptrap**:
   ```bash
   snmptrap -v 2c -c wg1Community 10.42.4.3:162 '' 1.3.6.1.4.1.3902.1082.500.2.1 1.3.6.1.2.1.1.3.0 s "Test Trap"
   ```

### Kafka Connection Issues

1. **Verify Kafka is accessible**:
   ```bash
   telnet 10.42.4.19 9092
   ```

2. **Check topic exists**:
   ```bash
   kafka-topics.sh --list --bootstrap-server 10.42.4.19:9092
   ```

3. **Create topics if needed**:
   ```bash
   kafka-topics.sh --create --topic olt_snmp_traps --bootstrap-server 10.42.4.19:9092 --partitions 3 --replication-factor 1
   kafka-topics.sh --create --topic olt_ont_registration --bootstrap-server 10.42.4.19:9092 --partitions 3 --replication-factor 1
   ```

4. **Consume registration events**:
   ```bash
   # Watch ONT registration events
   kafka-console-consumer.sh --bootstrap-server 10.42.4.19:9092 --topic olt_ont_registration --from-beginning
   
   # Watch all SNMP traps
   kafka-console-consumer.sh --bootstrap-server 10.42.4.19:9092 --topic olt_snmp_traps --from-beginning
   ```

## MIB Files

ZTE C320 OLT MIBs are included in the `MIB-C320/` directory. The application automatically parses these MIBs and builds a SQLite database for fast OID lookups.

### MIB Database Tools

**Build the database:**
```bash
./build_mib_db.sh
```

**Query the database:**
```bash
# Show statistics
python3 query_mib.py stats

# Look up specific OID
python3 query_mib.py oid 1.3.6.1.4.1.3902.1012.3

# Search by name (partial match)
python3 query_mib.py name ont

# List all notification traps
python3 query_mib.py traps
```

**Rebuild after adding new MIBs:**
```bash
# Just re-run the build script
./build_mib_db.sh
```

## Development

### Enable Debug Logging

Set in `.env`:
```
LOG_LEVEL=DEBUG
```

### Testing Locally

Use `snmptrap` command to send test traps:
```bash
snmptrap -v 2c -c wg1Community localhost:162 '' \
  1.3.6.1.4.1.3902.1082.500.2.1 \
  1.3.6.1.2.1.1.3.0 s "Test message"
```

## License

Internal use only.
