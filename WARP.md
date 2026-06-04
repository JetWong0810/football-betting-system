# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

A distributed football betting system with data scraping, analysis, and betting management. The system comprises three independent services containerized with Docker and deployed on an internal server, exposed to the internet via SSH tunnel.

### Infrastructure

| Role | Host | IP | Access |
|------|------|----|--------|
| Internal Server | mysql-backup | 10.130.130.139 | `ssh mysql-backup` |
| Public VPS | gouyun | 38.147.187.103 | `ssh gouyun` |
| Developer Machine | local | - | macOS |

### Services (all on mysql-backup via Docker)

| Service | Container | Port | Description |
|---------|-----------|------|-------------|
| MySQL 8.0 | football-mysql | 3321 | Database |
| API (FastAPI) | football-api | 7001 | Backend |
| Scraper | football-scraper | (internal) | Data sync every 10min |
| Frontend (Nginx) | football-frontend | 8088 | H5 web app |

### Network Architecture

```
User Browser → https://fc.jetwong.top
       ↓
VPS (38.147.187.103) nginx :443
       │ proxy_pass 127.0.0.1:5002
       ↓
SSH Reverse Tunnel (autossh, systemd: football-tunnel)
       ↓
Internal (10.130.130.139) :8088 nginx (football-frontend container)
       ├── /           → static files (Vue H5 build)
       ├── /api/       → proxy_pass http://football-api:7001/api/
       └── /static/    → proxy_pass http://football-api:7001/static/
```

Production URL: **https://fc.jetwong.top**

## Development Commands

### Local Development (Quick Start)

```bash
# Start all services locally (API + Frontend dev server)
./start-local.sh

# Stop all
./start-local.sh --stop

# Status
./start-local.sh --status
```

Local endpoints:
- Frontend: http://localhost:5173 (Vite dev server with hot-reload)
- API: http://localhost:7001
- API Docs: http://localhost:7001/docs

### API Service (FastAPI Backend)

```bash
cd api-service

# Install dependencies
pip3 install -r requirements.txt

# Run locally (development mode with auto-reload)
uvicorn main:app --host 0.0.0.0 --port 7001 --reload

# Test API
curl http://localhost:7001/api/health
```

**Environment Variables** (`api-service/.env`):
```env
MYSQL_HOST=10.130.130.139
MYSQL_PORT=3321
MYSQL_USER=root
MYSQL_PASSWORD=football_betting_2024
MYSQL_DATABASE=football_betting
WECHAT_APPID=wx5b2bc2de132728b8
WECHAT_SECRET=c4370b66b44a8f7f5a70bfd548007a8a
```

### Scraper Service

```bash
cd scraper-service

# Install dependencies
pip3 install -r requirements.txt

# Run manual scrape (executes once)
python3 main.py
```

### Frontend (UniApp H5)

```bash
cd frontend

# Install dependencies
npm install

# Development server (H5 build)
npm run dev:h5
# Opens at http://localhost:5173

# Production build
npm run build:h5
# Output: dist/build/h5/

# WeChat Mini Program development
npm run dev:mp-weixin

# WeChat Mini Program build
npm run build:mp-weixin
```

## Deployment

### Deploy to Internal Server (Docker)

All services are deployed as Docker containers on `mysql-backup` (10.130.130.139).

```bash
# One-command deploy (builds and starts everything)
bash deploy/deploy-remote.sh
```

The deploy script:
1. Packages api-service, scraper-service, frontend source code
2. Syncs to remote `/opt/football-betting-system/`
3. Runs `docker-compose up -d --build`

### Rebuild a Single Service

```bash
# SSH to server and rebuild only frontend
ssh mysql-backup "cd /opt/football-betting-system && docker-compose up -d --build frontend"

# Rebuild only API
ssh mysql-backup "cd /opt/football-betting-system && docker-compose up -d --build api"

# Rebuild only scraper
ssh mysql-backup "cd /opt/football-betting-system && docker-compose up -d --build scraper"
```

### Service Management (on mysql-backup)

```bash
# View all containers
ssh mysql-backup "cd /opt/football-betting-system && docker-compose ps"

# View logs
ssh mysql-backup "cd /opt/football-betting-system && docker-compose logs -f"
ssh mysql-backup "docker logs football-api --tail 50"
ssh mysql-backup "docker logs football-scraper --tail 50"

# Restart all
ssh mysql-backup "cd /opt/football-betting-system && docker-compose restart"

# Stop all
ssh mysql-backup "cd /opt/football-betting-system && docker-compose down"

# Restart tunnel (if connection drops)
ssh mysql-backup "systemctl restart football-tunnel"
ssh mysql-backup "systemctl status football-tunnel"
```

### SSH Tunnel Management

The reverse tunnel is managed by systemd on mysql-backup:

```bash
# Check tunnel status
ssh mysql-backup "systemctl status football-tunnel"

# Verify tunnel is working (on VPS)
ssh gouyun "ss -tlnp | grep 5002"

# Restart if connection drops
ssh mysql-backup "systemctl restart football-tunnel"
```

Service file: `/etc/systemd/system/football-tunnel.service`
Tunnel: VPS:5002 ← autossh → mysql-backup:8088

### VPS Nginx Config

Location: `/etc/nginx/sites-enabled/fc.jetwong.top`

The VPS nginx simply proxies HTTPS to the tunnel port:
- `fc.jetwong.top:443` → `proxy_pass http://127.0.0.1:5002`
- SSL cert: `/etc/nginx/ssl/fc.jetwong.top_chain.pem`

## Architecture

### System Flow

```
User Browser
    ↓ HTTPS
fc.jetwong.top (VPS nginx → SSH tunnel)
    ↓
Frontend (Nginx container @ mysql-backup:8088)
    ↓ /api/ proxy
API Service (FastAPI container @ mysql-backup:7001)
    ↓ MySQL
Database (MySQL 8.0 container @ mysql-backup:3321)
    ↑ Sync every 10 min
Scraper Service (Python container @ mysql-backup)
    ↓ HTTPS
External Sporttery API (China Sports Lottery)
```

### Data Flow

1. **Scraper Service** runs continuously in Docker, syncing every 10 minutes
   - Fetches match data from `webapi.sporttery.cn`
   - Writes to MySQL container via Docker network
   - Handles: HAD, HHAD, CRS, TTG, HAFU odds types

2. **API Service** runs in Docker, exposed on port 7001
   - RESTful API via FastAPI
   - User authentication (password + WeChat OAuth)
   - Betting records and strategy configuration

3. **Frontend** served by nginx container on port 8088
   - UniApp H5 build (Vue 3 + Vite)
   - Nginx handles `/api/` reverse proxy to API container
   - SPA fallback for client-side routing

### Database

**MySQL 8.0** running in Docker container `football-mysql`

Connection: `10.130.130.139:3321` (root / football_betting_2024 / football_betting)

**Key Tables**:
- `matches` - Match information (teams, leagues, dates, status)
- `odds_win_draw_lose` - Win/Draw/Lose odds (HAD/HHAD with handicap)
- `odds_correct_score` - Correct score predictions
- `odds_total_goals` - Total goals ranges
- `odds_half_full_time` - Half-time/full-time results
- `users` - User accounts (password + WeChat login)
- `user_configs` - Betting strategy configurations
- `user_bets` - Betting records
- `sync_status` - Last sync timestamp

### Code Organization

**Backend Services** (Python 3.9+):
- `database.py` - MySQL connection management
- `repository.py` - Data access layer with upsert methods
- `settings.py` - Configuration from environment variables
- `main.py` - FastAPI app (api-service) or scraper entry (scraper-service)

**API Service Specific**:
- `auth.py` - JWT token, password hashing (bcrypt)
- `user_repository.py` - User CRUD, bet records, configs

**Scraper Service Specific**:
- `scraper/sporttery_service.py` - Sporttery API client
- `entrypoint.py` - Loop wrapper for Docker (runs sync every N seconds)

**Frontend** (Vue 3 + UniApp):
- `stores/` - Pinia stores (user, bet, match, config, stat)
- `pages/` - Page components by feature
- `utils/http.js` - API client (BASE_URL is empty string in production, uses relative `/api/` paths)

### Authentication

**Dual Modes**:
1. **Password-based** (H5): JWT tokens, 7-day expiry, bcrypt
2. **WeChat OAuth** (Mini Program): code → openid, auto-create user

### Important Constraints

1. **Docker Network**: All services communicate via `football-net` Docker bridge. API and scraper connect to MySQL using hostname `mysql` (container name).

2. **Tunnel Dependency**: Public access requires the SSH tunnel (`football-tunnel` systemd service) to be running on mysql-backup.

3. **Port Allocation**: Chosen to avoid conflicts with existing services on mysql-backup:
   - 3316-3320: existing MySQL instances
   - 8001: we-mp-rss
   - 80/8081/8082: existing nginx
   - Our services: 3321, 7001, 8088

4. **Frontend API Path**: H5 production build uses empty `BASE_URL` — requests go to same-origin `/api/xxx`, nginx proxies to API container.

5. **Match Number Format**: 6 digits YYMMDD (e.g., 260604 = 2026-06-04).

## Testing

```bash
# Test via public URL
curl https://fc.jetwong.top/api/health
curl https://fc.jetwong.top/api/matches?page_size=10

# Test via internal IP directly
ssh mysql-backup "curl -s http://localhost:7001/api/health"
ssh mysql-backup "curl -s http://localhost:8088/api/matches?page_size=5"

# Test with authentication
TOKEN="your_jwt_token"
curl -H "Authorization: Bearer $TOKEN" https://fc.jetwong.top/api/user/profile
```

## Troubleshooting

### Site not accessible (fc.jetwong.top)
```bash
# 1. Check tunnel
ssh mysql-backup "systemctl status football-tunnel"
ssh gouyun "ss -tlnp | grep 5002"

# 2. Check containers
ssh mysql-backup "docker ps --filter 'name=football-'"

# 3. Check VPS nginx
ssh gouyun "nginx -t && curl -s http://127.0.0.1:5002/api/health"

# 4. Restart tunnel if needed
ssh mysql-backup "systemctl restart football-tunnel"
```

### API returns 500
```bash
# Check API logs
ssh mysql-backup "docker logs football-api --tail 50"

# Check MySQL is healthy
ssh mysql-backup "docker exec football-mysql mysqladmin ping -u root -pfootball_betting_2024"
```

### Scraper not syncing
```bash
ssh mysql-backup "docker logs football-scraper --tail 30"
```

### Frontend build fails
```bash
# Rebuild from scratch
ssh mysql-backup "cd /opt/football-betting-system && docker-compose build --no-cache frontend && docker-compose up -d frontend"
```

### Database connection from local
```bash
mysql -h 10.130.130.139 -P 3321 -u root -pfootball_betting_2024 football_betting
```

## File Structure (Deploy)

```
deploy/
├── docker-compose.yml          # Service orchestration (v2.4 format)
├── deploy-remote.sh            # One-command deploy script
├── init-sql/
│   └── 01_schema.sql           # Database initialization
├── api-service/
│   └── Dockerfile              # Python 3.9-slim + uvicorn
├── scraper-service/
│   ├── Dockerfile              # Python 3.9-slim
│   └── entrypoint.py           # Loop-mode wrapper
├── frontend/
│   ├── Dockerfile              # Node build + nginx serve
│   └── nginx.conf              # /api/ proxy + SPA fallback
└── wait-for-mysql.sh           # (backup) MySQL readiness check
```

## Code Style Notes

- **Python**: f-strings, type hints, dict-based data (no dataclasses)
- **FastAPI**: Pydantic models for validation
- **Vue**: Composition API with `<script setup>`
- **UniApp**: Conditional compilation (`#ifdef`, `#ifndef`) for platforms
- **Error Messages**: Chinese user-facing messages
- **SQL**: Parameterized queries (`%s` placeholders)
