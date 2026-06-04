#!/bin/bash
set -e

# Football Betting System - Deploy to 10.130.130.139 (via ssh mysql-backup)
# This script syncs files and starts services using docker-compose

SSH_HOST="mysql-backup"
REMOTE_DIR="/opt/football-betting-system"
LOCAL_PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Football Betting System - Remote Deploy${NC}"
echo -e "${GREEN}  Target: 10.130.130.139 (ssh mysql-backup)${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""

# Step 1: Prepare deploy directory with source code
echo -e "${YELLOW}[1/5] Preparing deployment package...${NC}"

# Create temp staging area
STAGING="/tmp/football-deploy-staging"
rm -rf "$STAGING"
mkdir -p "$STAGING"

# Copy docker-compose and configs
cp "$DEPLOY_DIR/docker-compose.yml" "$STAGING/"
cp -r "$DEPLOY_DIR/init-sql" "$STAGING/"

# Copy api-service source + Dockerfile
mkdir -p "$STAGING/api-service"
cp "$DEPLOY_DIR/api-service/Dockerfile" "$STAGING/api-service/"
# Copy api source files (exclude venv, __pycache__, etc.)
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' \
    --exclude='data/' --exclude='static/uploads/' \
    "$LOCAL_PROJECT/api-service/" "$STAGING/api-service/"
# Use deploy Dockerfile
cp "$DEPLOY_DIR/api-service/Dockerfile" "$STAGING/api-service/Dockerfile"
# Create stripped requirements (no OCR deps for lighter build)
grep -v -E "^(paddleocr|paddlepaddle|opencv-python|Pillow)" \
    "$LOCAL_PROJECT/api-service/requirements.txt" > "$STAGING/api-service/requirements.txt"

# Copy scraper-service source + Dockerfile + entrypoint
mkdir -p "$STAGING/scraper-service"
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' --exclude='data/' \
    "$LOCAL_PROJECT/scraper-service/" "$STAGING/scraper-service/"
cp "$DEPLOY_DIR/scraper-service/Dockerfile" "$STAGING/scraper-service/Dockerfile"
cp "$DEPLOY_DIR/scraper-service/entrypoint.py" "$STAGING/scraper-service/entrypoint.py"

# Copy frontend source + Dockerfile + nginx.conf
mkdir -p "$STAGING/frontend"
rsync -a --exclude='node_modules' --exclude='dist' --exclude='.env*' \
    "$LOCAL_PROJECT/frontend/" "$STAGING/frontend/"
cp "$DEPLOY_DIR/frontend/Dockerfile" "$STAGING/frontend/Dockerfile"
cp "$DEPLOY_DIR/frontend/nginx.conf" "$STAGING/frontend/nginx.conf"

echo -e "${GREEN}  ✓ Package prepared${NC}"

# Step 2: Sync to remote
echo -e "${YELLOW}[2/5] Syncing files to remote server...${NC}"

ssh "$SSH_HOST" "mkdir -p $REMOTE_DIR"
rsync -az --delete \
    --exclude='mysql_data' \
    "$STAGING/" "$SSH_HOST:$REMOTE_DIR/"

echo -e "${GREEN}  ✓ Files synced${NC}"

# Step 3: Stop existing containers (if any)
echo -e "${YELLOW}[3/5] Stopping existing containers (if any)...${NC}"

ssh "$SSH_HOST" "cd $REMOTE_DIR && docker-compose down 2>/dev/null || true"

echo -e "${GREEN}  ✓ Old containers stopped${NC}"

# Step 4: Build and start
echo -e "${YELLOW}[4/5] Building and starting services...${NC}"

ssh "$SSH_HOST" "cd $REMOTE_DIR && docker-compose up -d --build"

echo -e "${GREEN}  ✓ Services started${NC}"

# Step 5: Verify
echo -e "${YELLOW}[5/5] Verifying services...${NC}"

sleep 10

ssh "$SSH_HOST" "docker ps --filter 'name=football-' --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "${YELLOW}Services:${NC}"
echo -e "  MySQL:    10.130.130.139:3321"
echo -e "  API:      http://10.130.130.139:7001"
echo -e "  API Docs: http://10.130.130.139:7001/docs"
echo -e "  Frontend: http://10.130.130.139:8088"
echo ""
echo -e "${YELLOW}Management:${NC}"
echo -e "  ssh mysql-backup 'cd $REMOTE_DIR && docker-compose logs -f'"
echo -e "  ssh mysql-backup 'cd $REMOTE_DIR && docker-compose ps'"
echo -e "  ssh mysql-backup 'cd $REMOTE_DIR && docker-compose restart'"
echo -e "  ssh mysql-backup 'cd $REMOTE_DIR && docker-compose down'"

# Cleanup staging
rm -rf "$STAGING"
