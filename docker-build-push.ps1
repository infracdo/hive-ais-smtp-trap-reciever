# Docker Build and Push Script for SNMP Trap to Kafka Service (Windows PowerShell)
# 
# Prerequisites:
# - Docker Desktop installed and running
# - Docker Hub account
# - Logged into Docker Hub: docker login
# - MIB database built (.\build_mib_db.sh in WSL or Git Bash)
#
# Usage: .\docker-build-push.ps1 [username] [tag]
# Example: .\docker-build-push.ps1 myusername latest

param(
    [string]$DockerHubUsername = "marcandres888",
    [string]$Tag = "latest"
)

$ErrorActionPreference = "Stop"

# Configuration
$ImageName = "snmp-trap-kafka"
$FullImageName = "${DockerHubUsername}/${ImageName}:${Tag}"

Write-Host "=== SNMP Trap to Kafka - Docker Build & Push ===" -ForegroundColor Green
Write-Host "Docker Hub Username: $DockerHubUsername" -ForegroundColor Cyan
Write-Host "Image Name: $ImageName" -ForegroundColor Cyan
Write-Host "Tag: $Tag" -ForegroundColor Cyan
Write-Host "Full Image Name: $FullImageName" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
Write-Host "Checking Docker status..." -ForegroundColor Yellow
try {
    $dockerVersion = docker version --format "{{.Server.Version}}" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed"
    }
    Write-Host "✓ Docker is running (version: $dockerVersion)" -ForegroundColor Green
}
catch {
    Write-Host "✗ Error: Docker is not running. Please start Docker Desktop." -ForegroundColor Red
    Write-Host "  1. Start Docker Desktop from Windows Start menu" -ForegroundColor Yellow
    Write-Host "  2. Wait for the whale icon in system tray to be steady" -ForegroundColor Yellow
    Write-Host "  3. Run this script again" -ForegroundColor Yellow
    exit 1
}

# Check if MIB database exists
Write-Host "Checking MIB database..." -ForegroundColor Yellow
if (-Not (Test-Path "mib_database.db")) {
    Write-Host "✗ Error: mib_database.db not found!" -ForegroundColor Red
    Write-Host "Please build the MIB database first:" -ForegroundColor Yellow
    Write-Host "  In WSL/Git Bash: ./build_mib_db.sh" -ForegroundColor Gray
    Write-Host "  Or manually: python mib_parser.py MIB-C320/MIB/gponcmib mibs/zte mibs" -ForegroundColor Gray
    exit 1
}

$mibSize = (Get-Item "mib_database.db").Length / 1MB
Write-Host ("✓ MIB database found ({0:N1} MB)" -f $mibSize) -ForegroundColor Green

# Check if logged into Docker Hub
Write-Host "Checking Docker Hub authentication..." -ForegroundColor Yellow
try {
    $dockerInfo = docker info 2>$null | Select-String "Username:"
    if ($dockerInfo) {
        $currentUser = $dockerInfo.Line.Split(':')[1].Trim()
        Write-Host "✓ Logged into Docker Hub as: $currentUser" -ForegroundColor Green
        
        if ($currentUser -ne $DockerHubUsername) {
            Write-Host "⚠ Warning: You're logged in as '$currentUser' but specified username '$DockerHubUsername'" -ForegroundColor Yellow
            $continue = Read-Host "Continue anyway? (y/N)"
            if ($continue -ne 'y' -and $continue -ne 'Y') {
                Write-Host "Aborted by user." -ForegroundColor Red
                exit 1
            }
        }
    }
    else {
        Write-Host "✗ Not logged into Docker Hub. Please run: docker login" -ForegroundColor Red
        exit 1
    }
}
catch {
    Write-Host "✗ Could not verify Docker Hub login. Please run: docker login" -ForegroundColor Red
    exit 1
}

# Build the Docker image
Write-Host ""
Write-Host "Building Docker image..." -ForegroundColor Yellow
Write-Host "Command: docker build -t $FullImageName ." -ForegroundColor Gray

try {
    docker build -t $FullImageName .
    if ($LASTEXITCODE -ne 0) {
        throw "Docker build failed"
    }
    Write-Host "✓ Docker build successful!" -ForegroundColor Green
}
catch {
    Write-Host "✗ Docker build failed!" -ForegroundColor Red
    exit 1
}

# Show image details
Write-Host ""
Write-Host "Image details:" -ForegroundColor Yellow
docker images $FullImageName --format "table {{.Repository}}`t{{.Tag}}`t{{.ID}}`t{{.Size}}`t{{.CreatedAt}}"

# Test the image locally (optional)
Write-Host ""
$testLocal = Read-Host "Test the image locally first? (y/N)"
if ($testLocal -eq 'y' -or $testLocal -eq 'Y') {
    Write-Host "Starting container for local test..." -ForegroundColor Yellow
    Write-Host "Note: This requires SNMP traps on port 162 (host network mode)" -ForegroundColor Gray
    
    # Create test environment file
    @"
SNMP_LISTEN_HOST=0.0.0.0
SNMP_LISTEN_PORT=162
SNMP_COMMUNITY=public
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC=test_snmp_traps
KAFKA_REGISTRATION_TOPIC=test_ont_registration
LOG_LEVEL=INFO
"@ | Out-File -FilePath ".env.test" -Encoding ASCII
    
    try {
        $containerId = docker run -d --name snmp-test --network host --env-file .env.test $FullImageName 2>$null
        if ($LASTEXITCODE -eq 0 -and $containerId) {
            Write-Host "✓ Container started with ID: $containerId" -ForegroundColor Green
            Write-Host "Listening on: UDP port 162" -ForegroundColor Cyan
            Write-Host "Waiting 5 seconds for startup..." -ForegroundColor Gray
            Start-Sleep -Seconds 5
            
            Write-Host "Container logs:" -ForegroundColor Gray
            docker logs $containerId 2>&1 | Select-Object -First 20
            
            Write-Host ""
            Read-Host "Press Enter to stop test container and continue..."
            
            # Stop and remove test container
            docker stop $containerId | Out-Null
            docker rm $containerId | Out-Null
            Write-Host "✓ Test container stopped and removed" -ForegroundColor Green
        }
        else {
            Write-Host "✗ Container failed to start" -ForegroundColor Red
            $containerId = docker ps -a --filter "name=snmp-test" --format "{{.ID}}" | Select-Object -First 1
            if ($containerId) {
                Write-Host "Container logs:" -ForegroundColor Gray
                docker logs $containerId 2>&1 | Select-Object -First 20
                docker rm $containerId | Out-Null
            }
        }
    }
    catch {
        Write-Host "✗ Test failed: $_" -ForegroundColor Red
    }
    finally {
        Remove-Item ".env.test" -ErrorAction SilentlyContinue
    }
}

# Push to Docker Hub
Write-Host ""
$pushImage = Read-Host "Push image to Docker Hub? (Y/n)"
if ($pushImage -ne 'n' -and $pushImage -ne 'N') {
    Write-Host "Pushing to Docker Hub..." -ForegroundColor Yellow
    Write-Host "Command: docker push $FullImageName" -ForegroundColor Gray
    
    try {
        docker push $FullImageName
        if ($LASTEXITCODE -ne 0) {
            throw "Docker push failed"
        }
        
        Write-Host "✓ Successfully pushed to Docker Hub!" -ForegroundColor Green
        Write-Host ""
        Write-Host "=== Deployment Information ===" -ForegroundColor Green
        Write-Host "Image URL: $FullImageName" -ForegroundColor Cyan
        Write-Host "Docker Hub URL: https://hub.docker.com/r/${DockerHubUsername}/${ImageName}" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Use this image in your docker-compose.yml:" -ForegroundColor Yellow
        Write-Host "services:" -ForegroundColor Gray
        Write-Host "  snmp-to-kafka:" -ForegroundColor Gray
        Write-Host "    image: $FullImageName" -ForegroundColor Gray
        Write-Host "    network_mode: host" -ForegroundColor Gray
        Write-Host "    restart: unless-stopped" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Required environment variables:" -ForegroundColor Yellow
        Write-Host "  KAFKA_BOOTSTRAP_SERVERS=your_kafka_ip:9092" -ForegroundColor Gray
        Write-Host "  SNMP_COMMUNITY=your_community" -ForegroundColor Gray
    }
    catch {
        Write-Host "✗ Docker push failed!" -ForegroundColor Red
        exit 1
    }
}
else {
    Write-Host "Skipped pushing to Docker Hub." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Build Complete ===" -ForegroundColor Green

# Optional cleanup
Write-Host ""
$removeImage = Read-Host "Remove local image to save space? (y/N)"
if ($removeImage -eq 'y' -or $removeImage -eq 'Y') {
    docker rmi $FullImageName
    Write-Host "✓ Local image removed" -ForegroundColor Green
}
