#!/bin/bash

###############################################################################
# 足球竞彩系统一键部署脚本
# 
# 功能：自动部署三个服务（API、抓取、前端）
# 使用：./deploy.sh [选项]
#
# 选项：
#   --api-only      只部署 API 服务
#   --scraper-only  只部署抓取服务
#   --frontend-only 只部署前端服务
#   --skip-build    跳过前端构建（使用已构建的文件）
#   --help          显示帮助信息
###############################################################################

set -e  # 遇到错误立即退出
set -o pipefail  # 管道命令失败时也退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 服务器配置
GUIYUN_HOST="guiyun"
GUIYUN_IP="103.140.229.232"
MYSQL_BACKUP_HOST="mysql-backup"
MYSQL_BACKUP_IP="120.133.42.145"

# 项目配置
PROJECT_DIR="/opt/football-betting-system"
REPO_URL=""  # 如果为空，将从本地 Git 仓库自动获取
GIT_BRANCH="main"  # 默认分支，可通过 --branch 参数指定

# 数据库配置
MYSQL_ROOT_PASSWORD="football_betting_2024"
MYSQL_SYNC_USER="football_sync"
MYSQL_SYNC_PASSWORD="sync_pass_2024_secure"
MYSQL_DATABASE="football_betting"

# 证书配置
CERTS_DIR="$(pwd)/certs"
API_CERT_DIR="$CERTS_DIR/api.football.jetwong.top"
FRONTEND_CERT_DIR="$CERTS_DIR/www.jetwong.top"
REMOTE_CERT_BASE="/etc/nginx/ssl"

# 部署选项
DEPLOY_API=true
DEPLOY_SCRAPER=true
DEPLOY_FRONTEND=true
SKIP_BUILD=false

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --api-only)
            DEPLOY_API=true
            DEPLOY_SCRAPER=false
            DEPLOY_FRONTEND=false
            shift
            ;;
        --scraper-only)
            DEPLOY_API=false
            DEPLOY_SCRAPER=true
            DEPLOY_FRONTEND=false
            shift
            ;;
        --frontend-only)
            DEPLOY_API=false
            DEPLOY_SCRAPER=false
            DEPLOY_FRONTEND=true
            shift
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --branch)
            GIT_BRANCH="$2"
            shift 2
            ;;
        --help)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --api-only      只部署 API 服务"
            echo "  --scraper-only  只部署抓取服务"
            echo "  --frontend-only 只部署前端服务"
            echo "  --skip-build    跳过前端构建"
            echo "  --branch BRANCH 指定 Git 分支（默认: main）"
            echo "  --help          显示此帮助信息"
            exit 0
            ;;
        *)
            echo -e "${RED}未知选项: $1${NC}"
            echo "使用 --help 查看帮助信息"
            exit 1
            ;;
    esac
done

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查 HTTP/HTTPS 可访问性
check_url_accessible() {
    local url="$1"
    local label="$2"
    local retries="${3:-3}"
    local allowed_codes="${4:-200 301 302 304}"

    for ((attempt=1; attempt<=retries; attempt++)); do
        if http_code=$(curl -o /dev/null -s -w "%{http_code}" --max-time 10 "$url"); then
            if [[ " $allowed_codes " == *" $http_code "* ]]; then
                print_success "$label 可访问 (HTTP $http_code)"
                return 0
            fi
            print_warning "$label 第 $attempt 次检测返回 HTTP $http_code"
        else
            print_warning "$label 第 $attempt 次检测失败：无法连接或 DNS 解析失败"
        fi
        sleep 2
    done

    print_error "$label 无法访问，请检查 DNS、Nginx 或防火墙配置 ($url)"
    return 1
}

# 检查命令是否存在
check_command() {
    if ! command -v $1 &> /dev/null; then
        print_error "$1 未安装，请先安装"
        exit 1
    fi
}

# 同步证书到服务器
sync_certificate() {
    local host="$1"
    local domain="$2"
    local local_dir="$3"
    local remote_tmp="/tmp/${domain}-cert"
    local remote_dir="$REMOTE_CERT_BASE/$domain"

    if [ ! -d "$local_dir" ]; then
        print_error "证书目录 $local_dir 不存在，请先解压证书文件"
        exit 1
    fi

    print_info "同步 $domain 证书到 $host ..."
    rsync -avz --delete "$local_dir/" "$host:$remote_tmp/" >/dev/null
    ssh $host << EOF
        sudo mkdir -p "$remote_dir"
        sudo cp $remote_tmp/* "$remote_dir/"
        sudo chmod 600 "$remote_dir/"*
        rm -rf "$remote_tmp"
EOF
}

# 获取 Git 仓库 URL
get_repo_url() {
    if [ -z "$REPO_URL" ]; then
        # 尝试从本地 Git 仓库获取远程 URL
        if [ -d ".git" ]; then
            REPO_URL=$(git remote get-url origin 2>/dev/null || echo "")
            if [ -n "$REPO_URL" ]; then
                print_info "自动检测到 Git 仓库: $REPO_URL"
            fi
        fi
        
        # 如果仍然为空，提示输入
        if [ -z "$REPO_URL" ]; then
            read -p "请输入 Git 仓库地址: " REPO_URL
        fi
    fi
}

# 检查 SSH 连接
check_ssh() {
    local host=$1
    print_info "检查 $host 的 SSH 连接..."
    if ssh -o ConnectTimeout=5 -o BatchMode=yes $host "echo 'OK'" &> /dev/null; then
        print_success "$host SSH 连接正常"
        return 0
    else
        print_error "无法连接到 $host，请检查："
        echo "  1. SSH 密钥是否已配置"
        echo "  2. ~/.ssh/config 中是否配置了 $host"
        echo "  3. 网络连接是否正常"
        return 1
    fi
}

# 部署 API 服务
deploy_api() {
    print_info "开始部署 API 服务到 $GUIYUN_HOST..."
    
    # 检查 SSH 连接
    if ! check_ssh $GUIYUN_HOST; then
        return 1
    fi
    
    # 1. 准备环境
    print_info "准备服务器环境..."
    ssh $GUIYUN_HOST "sudo apt update && sudo apt install -y python3-pip python3-venv mysql-server mysql-client nginx git" || {
        print_error "环境准备失败"
        return 1
    }
    
    # 2. 克隆或更新代码
    get_repo_url
    print_info "克隆/更新代码..."
    if ssh $GUIYUN_HOST "[ -d $PROJECT_DIR ]"; then
        print_info "项目已存在，从 GitHub 拉取最新代码..."
        ssh $GUIYUN_HOST bash << GITEOF
            set +e  # 允许错误，以便更好的错误处理
            cd $PROJECT_DIR || exit 1
            
            # 获取远程更新
            git fetch origin 2>&1 || echo "警告: git fetch 失败，继续尝试 pull"
            
            # 检查远程分支是否存在
            if git ls-remote --heads origin $GIT_BRANCH 2>/dev/null | grep -q "$GIT_BRANCH"; then
                # 远程分支存在，切换到该分支
                if ! git checkout $GIT_BRANCH 2>/dev/null; then
                    # 如果本地分支不存在，创建并跟踪远程分支
                    git checkout -b $GIT_BRANCH origin/$GIT_BRANCH 2>/dev/null || {
                        echo "错误: 无法创建分支 $GIT_BRANCH"
                        exit 1
                    }
                fi
                git pull origin $GIT_BRANCH || {
                    echo "警告: git pull 失败，但继续部署"
                }
                echo "代码已更新到最新版本 (分支: $GIT_BRANCH)"
            else
                echo "警告: 远程分支 $GIT_BRANCH 不存在，使用当前分支"
                git pull 2>&1 || echo "警告: git pull 失败"
            fi
GITEOF
    else
        print_info "克隆项目..."
        ssh $GUIYUN_HOST "cd /opt && git clone -b $GIT_BRANCH $REPO_URL football-betting-system"
    fi
    
    # 3. 配置 MySQL
    print_info "配置 MySQL 数据库..."
    ssh $GUIYUN_HOST << EOF
        # 设置 root 密码
        sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '$MYSQL_ROOT_PASSWORD'; FLUSH PRIVILEGES;" 2>/dev/null || true
        
        # 创建数据库
        mysql -u root -p'$MYSQL_ROOT_PASSWORD' -e "CREATE DATABASE IF NOT EXISTS $MYSQL_DATABASE CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>/dev/null || true
        
        # 创建远程用户
        mysql -u root -p'$MYSQL_ROOT_PASSWORD' << SQL
CREATE USER IF NOT EXISTS '$MYSQL_SYNC_USER'@'$MYSQL_BACKUP_IP' IDENTIFIED BY '$MYSQL_SYNC_PASSWORD';
GRANT SELECT, INSERT, UPDATE ON $MYSQL_DATABASE.* TO '$MYSQL_SYNC_USER'@'$MYSQL_BACKUP_IP';
FLUSH PRIVILEGES;
SQL
        
        # 配置远程访问
        sudo sed -i 's/^bind-address.*/bind-address = 0.0.0.0/' /etc/mysql/mysql.conf.d/mysqld.cnf || true
        sudo systemctl restart mysql || true
EOF
    
    # 4. 部署 API 服务
    print_info "部署 API 服务..."
    ssh $GUIYUN_HOST << EOF
        cd $PROJECT_DIR/api-service
        
        # 创建虚拟环境
        if [ ! -d "venv" ]; then
            python3 -m venv venv
        fi
        
        # 安装/更新依赖
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt --quiet
        
        # 创建 .env 文件
        cat > .env << ENVEOF
# MySQL 数据库配置
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=$MYSQL_ROOT_PASSWORD
MYSQL_DATABASE=$MYSQL_DATABASE

# API 配置
SYNC_INTERVAL_SECONDS=600
HTTP_TIMEOUT=20
ENVEOF
        
        # 导入数据库表结构
        mysql -u root -p'$MYSQL_ROOT_PASSWORD' $MYSQL_DATABASE < schema_mysql.sql || true
        mysql -u root -p'$MYSQL_ROOT_PASSWORD' $MYSQL_DATABASE < schema_user.sql || true
        # 执行微信登录相关字段迁移（如果表已存在）
        mysql -u root -p'$MYSQL_ROOT_PASSWORD' $MYSQL_DATABASE < schema_user_wechat.sql || true
EOF
    
    # 5. 配置 Systemd 服务
    print_info "配置 Systemd 服务..."
    ssh $GUIYUN_HOST << EOF
        # 先停止旧服务（如果存在）
        sudo systemctl stop football-betting-api 2>/dev/null || true
        
        # 等待服务完全停止
        sleep 2
        
        # 检查并清理占用 7001 端口的进程
        PORT_PID=\$(sudo lsof -ti:7001 2>/dev/null || true)
        if [ -n "\$PORT_PID" ]; then
            echo "发现端口 7001 被进程 \$PORT_PID 占用，正在清理..."
            sudo kill -9 \$PORT_PID 2>/dev/null || true
            sleep 1
        fi
        
        # 再次确认端口已释放
        REMAINING_PID=\$(sudo lsof -ti:7001 2>/dev/null || true)
        if [ -n "\$REMAINING_PID" ]; then
            echo "警告: 端口 7001 仍被占用，尝试强制清理..."
            sudo kill -9 \$REMAINING_PID 2>/dev/null || true
            sleep 1
        fi
        
        # 创建 systemd 服务文件
        sudo bash -c 'cat > /etc/systemd/system/football-betting-api.service << SERVICEEOF
[Unit]
Description=Football Betting API Service
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR/api-service
Environment="PATH=$PROJECT_DIR/api-service/venv/bin"
ExecStart=$PROJECT_DIR/api-service/venv/bin/uvicorn main:app --host 0.0.0.0 --port 7001
Restart=always
RestartSec=10
# 确保服务停止时正确清理
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
SERVICEEOF'
        
        # 重新加载 systemd 配置
        sudo systemctl daemon-reload
        
        # 启用服务
        sudo systemctl enable football-betting-api
        
        # 启动服务
        sudo systemctl start football-betting-api
        
        # 等待服务启动
        sleep 3
        
        # 检查服务状态
        sudo systemctl status football-betting-api --no-pager || true
        
        # 检查端口是否成功监听
        if sudo lsof -ti:7001 >/dev/null 2>&1; then
            echo "✓ 服务已成功启动，端口 7001 正在监听"
        else
            echo "✗ 警告: 服务可能未成功启动，端口 7001 未监听"
            echo "查看详细日志: sudo journalctl -u football-betting-api -n 50"
        fi
EOF
    
    # 6. 配置证书与 Nginx
    print_info "配置 Nginx 反向代理..."
    sync_certificate $GUIYUN_HOST "api.football.jetwong.top" "$API_CERT_DIR"
    ssh $GUIYUN_HOST << 'NGINXEOF'
        sudo tee /etc/nginx/sites-available/api.football.jetwong.top > /dev/null << 'NGINXCONFIG'
server {
    listen 80;
    server_name api.football.jetwong.top;
    return 301 https://api.football.jetwong.top$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.football.jetwong.top;

    access_log /var/log/nginx/api.football.access.log;
    error_log /var/log/nginx/api.football.error.log;

    ssl_certificate /etc/nginx/ssl/api.football.jetwong.top/api.football.jetwong.top_chain.pem;
    ssl_certificate_key /etc/nginx/ssl/api.football.jetwong.top/api.football.jetwong.top_key.key;
    ssl_session_timeout 10m;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://127.0.0.1:7001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
NGINXCONFIG
        
        sudo ln -sf /etc/nginx/sites-available/api.football.jetwong.top /etc/nginx/sites-enabled/
        sudo nginx -t && sudo systemctl reload nginx
NGINXEOF
    
    # 7. 验证
    print_info "验证 API 服务..."
    sleep 3
    if ssh $GUIYUN_HOST "curl -s http://localhost:7001/api/health" | grep -q "ok"; then
        print_success "API 服务部署成功！"
        print_info "访问地址: https://api.football.jetwong.top/docs"
    else
        print_warning "API 服务可能未正常启动，请检查日志: ssh $GUIYUN_HOST 'sudo journalctl -u football-betting-api -n 50'"
    fi

    # 8. 检查对外域名
    local api_public_url="https://api.football.jetwong.top/api/health"
    print_info "检测 API 域名可访问性 ($api_public_url)..."
    if ! check_url_accessible "$api_public_url" "API 域名 api.football.jetwong.top"; then
        print_warning "API 域名不可访问，请确认 DNS 指向 $GUIYUN_IP，或稍后再运行脚本检测"
    fi
}

# 部署抓取服务
deploy_scraper() {
    print_info "开始部署抓取服务到 $MYSQL_BACKUP_HOST..."
    
    # 检查 SSH 连接
    if ! check_ssh $MYSQL_BACKUP_HOST; then
        return 1
    fi
    
    # 1. 检查 Docker 容器
    print_info "检查 Docker 容器..."
    if ! ssh $MYSQL_BACKUP_HOST "docker ps | grep -q py39-dev"; then
        print_error "py39-dev 容器未运行，请先启动容器"
        return 1
    fi
    
    # 2. 克隆或更新代码
    get_repo_url
    print_info "克隆/更新代码..."
    if ssh $MYSQL_BACKUP_HOST "[ -d $PROJECT_DIR ]"; then
        print_info "项目已存在，从 GitHub 拉取最新代码..."
        ssh $MYSQL_BACKUP_HOST bash << GITEOF
            set +e  # 允许错误，以便更好的错误处理
            cd $PROJECT_DIR || exit 1
            
            # 获取远程更新
            git fetch origin 2>&1 || echo "警告: git fetch 失败，继续尝试 pull"
            
            # 检查远程分支是否存在
            if git ls-remote --heads origin $GIT_BRANCH 2>/dev/null | grep -q "$GIT_BRANCH"; then
                # 远程分支存在，切换到该分支
                if ! git checkout $GIT_BRANCH 2>/dev/null; then
                    # 如果本地分支不存在，创建并跟踪远程分支
                    git checkout -b $GIT_BRANCH origin/$GIT_BRANCH 2>/dev/null || {
                        echo "错误: 无法创建分支 $GIT_BRANCH"
                        exit 1
                    }
                fi
                git pull origin $GIT_BRANCH || {
                    echo "警告: git pull 失败，但继续部署"
                }
                echo "代码已更新到最新版本 (分支: $GIT_BRANCH)"
            else
                echo "警告: 远程分支 $GIT_BRANCH 不存在，使用当前分支"
                git pull 2>&1 || echo "警告: git pull 失败"
            fi
GITEOF
    else
        print_info "克隆项目..."
        ssh $MYSQL_BACKUP_HOST "cd /opt && git clone -b $GIT_BRANCH $REPO_URL football-betting-system"
    fi
    
    # 3. 同步代码到容器
    print_info "同步代码到容器..."
    ssh $MYSQL_BACKUP_HOST << EOF
        # 将项目代码复制到容器的工作目录
        docker cp $PROJECT_DIR/scraper-service/. py39-dev:/workspace/scraper-service/
        echo "代码已同步到容器"
EOF
    
    # 4. 在容器内安装依赖和配置
    print_info "配置抓取服务..."
    ssh $MYSQL_BACKUP_HOST << EOF
        docker exec py39-dev bash -c "
            set +e  # 允许错误，以便更好的错误处理
            cd /workspace/scraper-service || exit 1
            
            # 安装依赖
            pip3 install -r requirements.txt --quiet 2>/dev/null || pip3 install -r requirements.txt
            
            # 创建 .env 文件
            cat > .env << ENVEOF
# MySQL 数据库配置（连接到 guiyun 服务器）
MYSQL_HOST=$GUIYUN_IP
MYSQL_PORT=3306
MYSQL_USER=$MYSQL_SYNC_USER
MYSQL_PASSWORD=$MYSQL_SYNC_PASSWORD
MYSQL_DATABASE=$MYSQL_DATABASE

# API 配置
HTTP_TIMEOUT=20
SYNC_INTERVAL_SECONDS=600

# 竞彩 API
SPORTTERY_API_URL=https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry
USER_AGENT=football-betting-system/1.0
ENVEOF
            
            echo '配置完成'
        "
EOF
    
    # 5. 配置定时任务
    print_info "配置定时任务..."
    ssh $MYSQL_BACKUP_HOST << EOF
        # 创建日志文件
        sudo touch /var/log/football_scraper.log
        sudo chmod 666 /var/log/football_scraper.log
        
        # 检查是否已存在定时任务
        if ! crontab -l 2>/dev/null | grep -q "football_scraper"; then
            (crontab -l 2>/dev/null; echo "*/10 * * * * docker exec py39-dev bash -c \"cd /workspace/scraper-service && python3 main.py\" >> /var/log/football_scraper.log 2>&1") | crontab -
            echo "定时任务已添加"
        else
            echo "定时任务已存在，跳过"
        fi
EOF
    
    print_success "抓取服务部署成功！"
    print_info "定时任务每 10 分钟执行一次"
    print_info "查看日志: ssh $MYSQL_BACKUP_HOST 'tail -f /var/log/football_scraper.log'"
}

# 部署前端服务
deploy_frontend() {
    print_info "开始部署前端服务到 $GUIYUN_HOST..."
    
    # 检查 SSH 连接
    if ! check_ssh $GUIYUN_HOST; then
        return 1
    fi
    
    # 1. 本地构建（如果未跳过）
    if [ "$SKIP_BUILD" = false ]; then
        print_info "在本地构建前端..."
        if [ ! -d "frontend" ]; then
            print_error "frontend 目录不存在，请确保在项目根目录执行"
            return 1
        fi
        
        cd frontend
        
        # 检查 Node.js
        if ! command -v npm &> /dev/null; then
            print_error "Node.js 未安装，请先安装 Node.js"
            return 1
        fi
        
        # 安装依赖
        print_info "安装前端依赖..."
        npm install
        
        # 构建
        print_info "构建前端..."
        npm run build:h5
        
        cd ..
    else
        print_info "跳过构建，使用已构建的文件..."
        if [ ! -d "frontend/dist/build/h5" ]; then
            print_error "构建文件不存在，请先构建或移除 --skip-build 选项"
            return 1
        fi
    fi
    
    # 2. 上传到服务器
    print_info "上传前端文件到服务器..."
    rsync -avz --delete frontend/dist/build/h5/ $GUIYUN_HOST:$PROJECT_DIR/frontend/dist/
    
    # 3. 配置证书与 Nginx
    print_info "配置 Nginx..."
    sync_certificate $GUIYUN_HOST "www.jetwong.top" "$FRONTEND_CERT_DIR"
    ssh $GUIYUN_HOST << 'NGINXEOF'
        set -e
        # 清理遗留的同名配置，避免旧文件继续生效导致 301 循环
        sudo rm -f /etc/nginx/sites-enabled/www.jetwong.top /etc/nginx/sites-enabled/www.jetwong.top.conf
        sudo rm -f /etc/nginx/sites-available/www.jetwong.top /etc/nginx/sites-available/www.jetwong.top.conf
        
        sudo tee /etc/nginx/sites-available/www.jetwong.top.conf > /dev/null <<'EOF'
server {
    listen 80;
    server_name jetwong.top;
    return 301 https://www.jetwong.top$request_uri;
}

server {
    listen 80;
    server_name www.jetwong.top;
    return 301 https://www.jetwong.top$request_uri;
}

server {
    listen 443 ssl http2;
    server_name www.jetwong.top;

    access_log /var/log/nginx/www.jetwong.top.access.log;
    error_log /var/log/nginx/www.jetwong.top.error.log;

    ssl_certificate /etc/nginx/ssl/www.jetwong.top/www.jetwong.top_chain.pem;
    ssl_certificate_key /etc/nginx/ssl/www.jetwong.top/www.jetwong.top_key.key;
    ssl_session_timeout 10m;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    root /opt/football-betting-system/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/x-javascript application/xml+rss application/json;
}
EOF
        
        sudo ln -sf /etc/nginx/sites-available/www.jetwong.top.conf /etc/nginx/sites-enabled/www.jetwong.top.conf
        sudo nginx -t && sudo systemctl reload nginx
NGINXEOF
    
    print_success "前端服务部署成功！"
    print_info "访问地址: https://www.jetwong.top"

    # 4. 检测域名可访问性
    print_info "检测前端域名可访问性..."
    local frontend_urls=("https://www.jetwong.top")
    for url in "${frontend_urls[@]}"; do
        if ! check_url_accessible "$url" "$url"; then
            print_warning "$url 检测失败，请确认 DNS 解析、Nginx 配置及缓存情况"
        fi
    done
}

# 主函数
main() {
    print_info "=========================================="
    print_info "  足球竞彩系统一键部署脚本"
    print_info "=========================================="
    echo ""
    
    # 检查必要命令
    check_command ssh
    check_command rsync
    check_command curl
    
    # 显示部署计划
    echo ""
    print_info "部署计划:"
    [ "$DEPLOY_API" = true ] && echo "  ✓ API 服务 -> $GUIYUN_HOST"
    [ "$DEPLOY_SCRAPER" = true ] && echo "  ✓ 抓取服务 -> $MYSQL_BACKUP_HOST"
    [ "$DEPLOY_FRONTEND" = true ] && echo "  ✓ 前端服务 -> $GUIYUN_HOST"
    echo ""
    
    read -p "确认开始部署? (y/N): " confirm
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        print_info "已取消部署"
        exit 0
    fi
    
    # 执行部署
    if [ "$DEPLOY_API" = true ]; then
        deploy_api
        echo ""
    fi
    
    if [ "$DEPLOY_SCRAPER" = true ]; then
        deploy_scraper
        echo ""
    fi
    
    if [ "$DEPLOY_FRONTEND" = true ]; then
        deploy_frontend
        echo ""
    fi
    
    # 总结
    print_success "=========================================="
    print_success "  部署完成！"
    print_success "=========================================="
    echo ""
    print_info "访问地址:"
    [ "$DEPLOY_API" = true ] && echo "  - API 文档: https://api.football.jetwong.top/docs"
    [ "$DEPLOY_FRONTEND" = true ] && echo "  - 前端应用: https://www.jetwong.top"
    echo ""
    print_info "查看服务状态:"
    [ "$DEPLOY_API" = true ] && echo "  - API: ssh $GUIYUN_HOST 'sudo systemctl status football-betting-api'"
    [ "$DEPLOY_SCRAPER" = true ] && echo "  - 抓取日志: ssh $MYSQL_BACKUP_HOST 'tail -f /var/log/football_scraper.log'"
}

# 运行主函数
main

