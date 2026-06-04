#!/bin/bash
set -e

# Football Betting System - Deploy to remote server (via ssh mysql-backup)
# Pulls latest code from GitHub and rebuilds Docker services

SSH_HOST="mysql-backup"
REMOTE_DIR="/opt/football-betting-system"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Football Betting System - Remote Deploy${NC}"
echo -e "${GREEN}  Target: ssh $SSH_HOST${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""

# Step 1: Check if repo exists on remote, clone if not
echo -e "${YELLOW}[1/4] Checking remote repository...${NC}"

ssh "$SSH_HOST" "
if [ -d $REMOTE_DIR/.git ]; then
    echo 'Git repo exists, pulling latest...'
    cd $REMOTE_DIR && git pull origin main
else
    echo 'Cloning repository...'
    rm -rf $REMOTE_DIR
    git clone https://github.com/JetWong0810/football-betting-system.git $REMOTE_DIR
fi
"

echo -e "${GREEN}  ✓ Code updated${NC}"

# Step 2: Ensure .env exists
echo -e "${YELLOW}[2/4] Checking environment config...${NC}"

ssh "$SSH_HOST" "
if [ ! -f $REMOTE_DIR/deploy/.env ]; then
    echo 'ERROR: deploy/.env not found! Copy from .env.example and fill in values.'
    exit 1
fi
echo '.env file exists'
"

echo -e "${GREEN}  ✓ Config verified${NC}"

# Step 3: Build and start
echo -e "${YELLOW}[3/4] Building and starting services...${NC}"

ssh "$SSH_HOST" "cd $REMOTE_DIR/deploy && docker-compose up -d --build"

echo -e "${GREEN}  ✓ Services started${NC}"

# Step 4: Verify
echo -e "${YELLOW}[4/4] Verifying services...${NC}"

sleep 10

ssh "$SSH_HOST" "docker ps --filter 'name=football-' --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "${YELLOW}Services:${NC}"
echo -e "  Frontend: https://fc.jetwong.top"
echo -e "  API Docs: https://fc.jetwong.top/api/docs"
echo ""
echo -e "${YELLOW}Management:${NC}"
echo -e "  ssh $SSH_HOST 'cd $REMOTE_DIR/deploy && docker-compose logs -f'"
echo -e "  ssh $SSH_HOST 'cd $REMOTE_DIR/deploy && docker-compose ps'"
echo -e "  ssh $SSH_HOST 'cd $REMOTE_DIR/deploy && docker-compose restart'"
echo -e "  ssh $SSH_HOST 'cd $REMOTE_DIR/deploy && docker-compose down'"
