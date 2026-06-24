#!/bin/bash
# Docker Build and Push Script for SNMP Trap to Kafka Service (Linux/Mac)
# 
# Prerequisites:
# - Docker installed and running
# - Docker Hub account
# - Logged into Docker Hub: docker login
# - MIB database built (./build_mib_db.sh)
#
# Usage: ./docker-build-push.sh [username] [tag]
# Example: ./docker-build-push.sh myusername latest

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;37m'
NC='\033[0m' # No Color

# Default configuration
DEFAULT_DOCKER_HUB_USERNAME="marcandres888"

# Configuration
IMAGE_NAME="snmp-trap-kafka"
DOCKER_HUB_USERNAME="${1:-$DEFAULT_DOCKER_HUB_USERNAME}"
TAG="${2:-latest}"

FULL_IMAGE_NAME="${DOCKER_HUB_USERNAME}/${IMAGE_NAME}:${TAG}"

echo -e "${GREEN}=== SNMP Trap to Kafka - Docker Build & Push ===${NC}"
echo -e "${CYAN}Docker Hub Username: ${DOCKER_HUB_USERNAME}${NC}"
echo -e "${CYAN}Image Name: ${IMAGE_NAME}${NC}"
echo -e "${CYAN}Tag: ${TAG}${NC}"
echo -e "${CYAN}Full Image Name: ${FULL_IMAGE_NAME}${NC}"
echo ""

# Check if Docker is running
echo -e "${YELLOW}Checking Docker status...${NC}"
if ! docker version >/dev/null 2>&1; then
    echo -e "${RED}✗ Docker is not running${NC}"
    echo -e "${YELLOW}Attempting to start Docker...${NC}"
    
    # Try to start Docker service (WSL/Linux)
    if sudo service docker start >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Docker started successfully${NC}"
        sleep 2  # Give Docker a moment to fully start
    else
        echo -e "${RED}✗ Error: Could not start Docker.${NC}"
        echo -e "${YELLOW}Please start Docker manually:${NC}"
        echo -e "${GRAY}  sudo service docker start${NC}"
        exit 1
    fi
fi

DOCKER_VERSION=$(docker version --format "{{.Server.Version}}" 2>/dev/null)
echo -e "${GREEN}✓ Docker is running (version: ${DOCKER_VERSION})${NC}"

# Check if MIB database exists
echo -e "${YELLOW}Checking MIB database...${NC}"
if [ ! -f "mib_database.db" ]; then
    echo -e "${RED}✗ Error: mib_database.db not found!${NC}"
    echo -e "${YELLOW}Please build the MIB database first:${NC}"
    echo -e "${GRAY}  ./build_mib_db.sh${NC}"
    exit 1
fi

MIB_DB_SIZE=$(du -h mib_database.db | cut -f1)
echo -e "${GREEN}✓ MIB database found (${MIB_DB_SIZE})${NC}"

# Check if logged into Docker Hub
echo -e "${YELLOW}Checking Docker Hub authentication...${NC}"
DOCKER_INFO=$(docker info 2>/dev/null | grep -i "username:" || echo "")
if [ -n "$DOCKER_INFO" ]; then
    CURRENT_USER=$(echo "$DOCKER_INFO" | cut -d':' -f2 | tr -d ' ')
    echo -e "${GREEN}✓ Logged into Docker Hub as: ${CURRENT_USER}${NC}"
    
    if [ "$CURRENT_USER" != "$DOCKER_HUB_USERNAME" ]; then
        echo -e "${YELLOW}⚠ Warning: You're logged in as '${CURRENT_USER}' but specified username '${DOCKER_HUB_USERNAME}'${NC}"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${RED}Aborted by user.${NC}"
            exit 1
        fi
    fi
else
    # Alternative check: try to get credentials from config
    if [ -f ~/.docker/config.json ] && grep -q "auths" ~/.docker/config.json 2>/dev/null; then
        echo -e "${YELLOW}⚠ Docker credentials found but username not shown in docker info${NC}"
        echo -e "${YELLOW}This is normal for some Docker configurations.${NC}"
        read -p "Continue with build? (Y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            echo -e "${RED}Aborted by user.${NC}"
            echo -e "${YELLOW}To login, run: docker login${NC}"
            exit 1
        fi
    else
        echo -e "${RED}✗ Not logged into Docker Hub.${NC}"
        echo -e "${YELLOW}Attempting to login now...${NC}"
        if docker login; then
            echo -e "${GREEN}✓ Successfully logged in${NC}"
        else
            echo -e "${RED}✗ Login failed. Please run: docker login${NC}"
            exit 1
        fi
    fi
fi

# Build the Docker image
echo ""
echo -e "${YELLOW}Building Docker image...${NC}"
echo -e "${GRAY}Command: docker build -t ${FULL_IMAGE_NAME} .${NC}"

if docker build -t "$FULL_IMAGE_NAME" .; then
    echo -e "${GREEN}✓ Docker build successful!${NC}"
else
    echo -e "${RED}✗ Docker build failed!${NC}"
    exit 1
fi

# Show image details
echo ""
echo -e "${YELLOW}Image details:${NC}"
docker images "$FULL_IMAGE_NAME" --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}\t{{.CreatedAt}}"

# Test the image locally (optional)
echo ""
read -p "Test the image locally first? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Starting container for local test...${NC}"
    echo -e "${GRAY}Note: This requires SNMP traps on port 162 (privileged mode)${NC}"
    
    # Create test environment file
    cat > .env.test << EOF
SNMP_LISTEN_HOST=0.0.0.0
SNMP_LISTEN_PORT=162
SNMP_COMMUNITY=public
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC=test_snmp_traps
KAFKA_REGISTRATION_TOPIC=test_ont_registration
LOG_LEVEL=INFO
EOF
    
    CONTAINER_ID=$(docker run -d --name snmp-test --network host --env-file .env.test "$FULL_IMAGE_NAME" 2>/dev/null || echo "")
    if [ -n "$CONTAINER_ID" ]; then
        echo -e "${GREEN}✓ Container started with ID: ${CONTAINER_ID}${NC}"
        echo -e "${CYAN}Listening on: UDP port 162${NC}"
        echo -e "${GRAY}Waiting 5 seconds for startup...${NC}"
        sleep 5
        
        echo -e "${GRAY}Container logs:${NC}"
        docker logs "$CONTAINER_ID" 2>&1 | head -20
        
        echo ""
        echo "Press any key to stop test container and continue..."
        read -n 1 -s -r
        
        # Stop and remove test container
        docker stop "$CONTAINER_ID" >/dev/null 2>&1
        docker rm "$CONTAINER_ID" >/dev/null 2>&1
        rm -f .env.test
        echo -e "${GREEN}✓ Test container stopped and removed${NC}"
    else
        echo -e "${RED}✗ Container failed to start${NC}"
        CONTAINER_ID=$(docker ps -a --filter "name=snmp-test" --format "{{.ID}}" | head -n 1)
        if [ -n "$CONTAINER_ID" ]; then
            echo -e "${GRAY}Container logs:${NC}"
            docker logs "$CONTAINER_ID" 2>&1 | head -20
            docker rm "$CONTAINER_ID" >/dev/null 2>&1
        fi
        rm -f .env.test
    fi
fi

# Push to Docker Hub
echo ""
read -p "Push image to Docker Hub? (Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo -e "${YELLOW}Pushing to Docker Hub...${NC}"
    echo -e "${GRAY}Command: docker push ${FULL_IMAGE_NAME}${NC}"
    
    if docker push "$FULL_IMAGE_NAME"; then
        echo -e "${GREEN}✓ Successfully pushed to Docker Hub!${NC}"
        echo ""
        echo -e "${GREEN}=== Deployment Information ===${NC}"
        echo -e "${CYAN}Image URL: ${FULL_IMAGE_NAME}${NC}"
        echo -e "${CYAN}Docker Hub URL: https://hub.docker.com/r/${DOCKER_HUB_USERNAME}/${IMAGE_NAME}${NC}"
        echo ""
        echo -e "${YELLOW}Use this image in your docker-compose.yml:${NC}"
        echo -e "${GRAY}services:${NC}"
        echo -e "${GRAY}  snmp-to-kafka:${NC}"
        echo -e "${GRAY}    image: ${FULL_IMAGE_NAME}${NC}"
        echo -e "${GRAY}    network_mode: host${NC}"
        echo -e "${GRAY}    restart: unless-stopped${NC}"
        echo ""
        echo -e "${YELLOW}Required environment variables:${NC}"
        echo -e "${GRAY}  KAFKA_BOOTSTRAP_SERVERS=your_kafka_ip:9092${NC}"
        echo -e "${GRAY}  SNMP_COMMUNITY=your_community${NC}"
    else
        echo -e "${RED}✗ Docker push failed!${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}Skipped pushing to Docker Hub.${NC}"
fi

echo ""
echo -e "${GREEN}=== Build Complete ===${NC}"

# Optional cleanup
echo ""
read -p "Remove local image to save space? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker rmi "$FULL_IMAGE_NAME"
    echo -e "${GREEN}✓ Local image removed${NC}"
fi