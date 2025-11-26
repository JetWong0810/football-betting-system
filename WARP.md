# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

A distributed football betting system with data scraping, analysis, and betting management. The system comprises three independent services deployed across different servers:

1. **Scraper Service** - Deployed on `mysql-backup` server (120.133.42.145)
2. **API Service** - Deployed on `guiyun` server (103.140.229.232)
3. **Frontend** - Deployed on `guiyun` server (103.140.229.232)

Production URLs:
- Frontend: https://www.jetwong.top
- API: https://api.football.jetwong.top
- API Health: https://api.football.jetwong.top/api/health
- API Docs: https://api.football.jetwong.top/docs

## Development Commands

### API Service (FastAPI Backend)

```bash
cd api-service

# Install dependencies
pip3 install -r requirements.txt

# Run locally (development mode with auto-reload)
python3 main.py
# OR
uvicorn main:app --host 0.0.0.0 --port 7001 --reload

# Test API locally
curl http://localhost:7001/api/health

# View API documentation
open http://localhost:7001/docs
```

**Environment Variables** (create `.env` in `api-service/`):
```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=football_betting
WECHAT_APPID=your_appid
WECHAT_SECRET=your_secret
```

### Scraper Service

```bash
cd scraper-service

# Install dependencies
pip3 install -r requirements.txt

# Run manual scrape (executes once)
python3 main.py
```

**Environment Variables** (create `.env` in `scraper-service/`):
```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=football_betting
HTTP_TIMEOUT=20
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

### Database Setup (Local Development)

```bash
# Start MySQL
# macOS:
brew services start mysql
# Linux:
sudo systemctl start mysql

# Create database
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS football_betting CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# Import schema
mysql -u root -p football_betting < api-service/schema_mysql.sql
```

### Running All Services Locally

```bash
# Terminal 1: Start MySQL (if not running)
brew services start mysql  # macOS
# OR
sudo systemctl start mysql  # Linux

# Terminal 2: Start API service
cd api-service
export MYSQL_HOST=localhost MYSQL_USER=root MYSQL_PASSWORD=your_password MYSQL_DATABASE=football_betting
python3 main.py

# Terminal 3: Start frontend
cd frontend
npm run dev:h5

# Terminal 4 (optional): Run scraper once
cd scraper-service
export MYSQL_HOST=localhost MYSQL_USER=root MYSQL_PASSWORD=your_password MYSQL_DATABASE=football_betting
python3 main.py
```

### Deployment

```bash
# From project root, deploy all services
./deploy.sh

# Deploy individual services
./deploy.sh --api-only        # API service only
./deploy.sh --scraper-only    # Scraper service only
./deploy.sh --frontend-only   # Frontend only

# Deploy from a specific branch
./deploy.sh --branch develop

# Frontend deploy without rebuilding
./deploy.sh --frontend-only --skip-build
```

### Production Service Management (on servers)

```bash
# API service (on guiyun server)
ssh guiyun
sudo systemctl status football-betting-api
sudo systemctl restart football-betting-api
sudo journalctl -u football-betting-api -f   # View logs

# Check scraper cron (on mysql-backup server)
ssh mysql-backup
crontab -l
tail -f /var/log/football_scraper.log
```

## Architecture

### System Flow

```
User Browser
    ↓
Frontend (UniApp H5 @ guiyun)
    ↓ HTTPS
API Service (FastAPI @ guiyun, port 7001)
    ↓ MySQL
Database (MySQL @ guiyun)
    ↑ Sync every 10 min
Scraper Service (Cron @ mysql-backup)
    ↓ HTTPS
External Sporttery API (China Sports Lottery)
```

### Data Flow Architecture

1. **Scraper Service** runs on mysql-backup server every 10 minutes via cron
   - Fetches match data from `webapi.sporttery.cn`
   - Writes to remote MySQL database on guiyun server (10.130.147.121:3306)
   - Handles: HAD (Win/Draw/Lose), HHAD (Handicap), CRS (Correct Score), TTG (Total Goals), HAFU (Half-time/Full-time)

2. **API Service** runs on guiyun server as systemd service
   - Serves RESTful API on port 7001
   - Reads from local MySQL database
   - Does NOT scrape data (that's scraper service's job)
   - Provides user authentication (password-based and WeChat OAuth)
   - Manages user betting records and configurations

3. **Frontend** served via Nginx on guiyun server
   - UniApp-based H5 application (Vue 3 + Vite)
   - State management via Pinia stores
   - Can also be built as WeChat Mini Program

### Database Architecture

**Single MySQL Database**: `football_betting` on guiyun server

**Key Tables**:
- `matches` - Match information (teams, leagues, dates, status)
- `odds_win_draw_lose` - Win/Draw/Lose odds (HAD/HHAD with handicap)
- `odds_correct_score` - Correct score predictions (home_score, away_score)
- `odds_total_goals` - Total goals ranges (min_goals, max_goals)
- `odds_half_full_time` - Half-time and full-time result combinations
- `users` - User accounts (supports both password and WeChat login)
- `user_configs` - User betting strategy configurations
- `user_bets` - Betting records with status tracking
- `sync_status` - Tracks last data synchronization

**Key Patterns**:
- All odds tables use `ON DUPLICATE KEY UPDATE` for upsert operations
- Match filtering uses `match_timestamp` and `match_status` to show only available matches
- `match_number` (format: YYMMDD) is used for issue/period identification
- Correct score table uses `-1` for home/away scores when representing "other" outcomes (avoids NULL in unique indexes)

### Code Organization

**Backend Services** (Python 3.9+):
- `database.py` - MySQL connection management with context manager pattern
- `repository.py` - Data access layer with upsert methods for all odds types
- `settings.py` - Configuration from environment variables
- `main.py` - FastAPI application entry point (api-service) or scraper entry (scraper-service)

**API Service Specific**:
- `auth.py` - JWT token generation, password hashing (bcrypt), token verification
- `user_repository.py` - User CRUD operations, bet records, user configs
- `tasks.py` - Scheduled sync jobs (DEPRECATED - now handled by scraper service)

**Scraper Service Specific**:
- `scraper/sporttery_service.py` - Fetches and parses data from Sporttery API

**Frontend** (Vue 3 + UniApp):
- `stores/` - Pinia stores for state management:
  - `userStore.js` - Authentication, user profile
  - `betStore.js` - Betting records management
  - `betCartStore.js` - Shopping cart for multi-match bets
  - `matchStore.js` - Match data and odds
  - `configStore.js` - User betting strategy configs
  - `statStore.js` - Statistics and analytics
- `pages/` - Page components organized by feature
- `utils/` - Utility modules:
  - `http.js` - API client with request/response interceptors
  - `auth.js` - Route guards and authentication helpers
  - `kelly.js` - Kelly criterion calculator
  - `fixedRatio.js` - Fixed ratio betting calculator

### Authentication System

**Dual Authentication Modes**:
1. **Password-based** (H5 web app):
   - JWT tokens with 7-day expiration
   - Password hashing via bcrypt
   - Token stored in localStorage (web) or local storage (UniApp)

2. **WeChat OAuth** (Mini Program):
   - Silent login via `wx.login()` → code → openid
   - Full login with `wx.getUserProfile()` for nickname/avatar
   - Server-side decryption of encrypted user data
   - Avatar upload via base64 encoding
   - Automatic user creation on first login

**API Authentication**:
- `require_auth` dependency for protected endpoints
- Bearer token in `Authorization` header
- Returns 401 with friendly Chinese error messages

**Frontend Auth Guards**:
- Route interceptors in `App.vue` (navigateTo/switchTab)
- Auth-required pages listed in `utils/auth.js`
- Redirects to login page when needed
- Auto-login attempt on app launch (WeChat Mini Program only)

### Key Business Logic

**Match Filtering Logic** (in `api-service/repository.py`):
- Shows only matches that are "Selling" or "not_started" (filters out finished/cancelled)
- Uses Beijing timezone (UTC+8) for cutoff time calculations
- Cutoff rules: Monday-Thursday 22:00, Friday-Sunday 23:00
- Derives sale date from `match_number` (YYMMDD format)
- Filters out matches before today or past cutoff time

**Betting Strategy Calculators**:
- **Kelly Criterion** (`frontend/src/utils/kelly.js`):
  - Calculates optimal bet size based on edge and odds
  - Formula: `f = (bp - q) / b` where p=win probability, q=lose probability, b=net odds
  - Supports fractional Kelly (kelly_factor from user config)
  
- **Fixed Ratio** (`frontend/src/utils/fixedRatio.js`):
  - Bets fixed percentage of current capital
  - Uses `fixed_ratio` from user config (default 3%)

- **Stop Loss** (`frontend/src/utils/stopLoss.js`):
  - Tracks consecutive losses
  - Alerts when hitting `stop_loss_limit` (default 3)

### WeChat Integration Notes

**Mini Program Setup**:
- Requires `WECHAT_APPID` and `WECHAT_SECRET` env vars
- Uses official WeChat API: `api.weixin.qq.com`
- AES decryption for encrypted user data (CBC mode, PKCS7 padding)
- SHA1 signature verification for data integrity

**Avatar Handling**:
- Mini program can't directly access `avatarUrl` (privacy restrictions since 2021)
- Frontend base64-encodes avatar from `wx.chooseImage()`
- Backend saves to `static/uploads/` with UUID filename
- Returns full URL: `https://api.football.jetwong.top/static/uploads/{filename}`

### Important Constraints

1. **Network Isolation**: API service on guiyun CANNOT access external Sporttery API (firewall restrictions). Data scraping MUST happen on mysql-backup server.

2. **Database Access**: Both services connect to the SAME MySQL instance on guiyun (10.130.147.121 internal IP, or 103.140.229.232 external).

3. **Deployment Separation**: 
   - Scraper runs in Docker container `py39-dev` on mysql-backup
   - API runs as systemd service on guiyun
   - Frontend is static files served by Nginx on guiyun

4. **Match Number Format**: Always 6 digits YYMMDD (e.g., 251125 = 2025-11-25). Used for sorting and period identification.

5. **Odds Updates**: Real-time odds updates depend on scraper service running every 10 minutes. API service only reads cached data.

## Testing

```bash
# Test API endpoints
curl http://localhost:7001/api/health
curl http://localhost:7001/api/matches
curl http://localhost:7001/api/matches/{match_id}

# Test with authentication
TOKEN="your_jwt_token"
curl -H "Authorization: Bearer $TOKEN" http://localhost:7001/api/user/profile

# Test scraper
cd scraper-service
python3 main.py  # Should output match/odds count
```

## Troubleshooting

### API Service Won't Start
```bash
# Check logs
ssh guiyun
sudo journalctl -u football-betting-api -n 50

# Check if port 7001 is in use
lsof -i :7001

# Verify database connection
mysql -h localhost -u root -p football_betting -e "SHOW TABLES;"
```

### Scraper Not Running
```bash
# Check cron job
ssh mysql-backup
crontab -l

# Check scraper logs
tail -f /var/log/football_scraper.log

# Test manual run
docker exec py39-dev bash -c 'cd /workspace/scraper-service && python3 main.py'
```

### Frontend Build Fails
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
npm run build:h5
```

### Database Connection Issues
- Verify `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD` environment variables
- Check firewall rules (port 3306)
- Ensure MySQL service is running: `systemctl status mysql`
- For remote connections, verify user has proper host permissions in MySQL

## Code Style Notes

- **Python**: Uses f-strings, type hints, dataclasses avoided (dict-based)
- **FastAPI**: Pydantic models for request/response validation
- **Vue**: Composition API with `<script setup>`
- **UniApp**: Uses conditional compilation (`#ifdef`, `#ifndef`) for platform-specific code
- **Error Handling**: FastAPI exceptions with Chinese user-facing messages
- **Database**: All SQL uses parameterized queries (`%s` placeholders for MySQL)
