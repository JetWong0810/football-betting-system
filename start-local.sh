#!/bin/bash

# Football Betting System - Local Services Startup Script
# Usage: ./start-local.sh [--stop]

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$PROJECT_ROOT/api-service"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# PID files
API_PID_FILE="/tmp/football-betting-api.pid"
FRONTEND_PID_FILE="/tmp/football-betting-frontend.pid"

# Log files
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
API_LOG="$LOG_DIR/api-service.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function: Print colored message
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function: Check if process is running
is_running() {
    local pid_file=$1
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        else
            rm -f "$pid_file"
            return 1
        fi
    fi
    return 1
}

# Function: Stop service
stop_service() {
    local name=$1
    local pid_file=$2
    
    if is_running "$pid_file"; then
        local pid=$(cat "$pid_file")
        print_message "$YELLOW" "停止 $name (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 2
        
        # Force kill if still running
        if ps -p "$pid" > /dev/null 2>&1; then
            print_message "$YELLOW" "强制停止 $name..."
            kill -9 "$pid" 2>/dev/null || true
        fi
        
        rm -f "$pid_file"
        print_message "$GREEN" "✓ $name 已停止"
    else
        print_message "$YELLOW" "$name 未运行"
    fi
}

# Function: Stop all services
stop_all() {
    print_message "$YELLOW" "=== 停止所有服务 ==="
    stop_service "API Service" "$API_PID_FILE"
    stop_service "Frontend" "$FRONTEND_PID_FILE"
    
    # Also kill by port
    print_message "$YELLOW" "清理端口占用..."
    lsof -ti:7001 | xargs kill -9 2>/dev/null || true
    lsof -ti:5173 | xargs kill -9 2>/dev/null || true
    
    print_message "$GREEN" "所有服务已停止"
    exit 0
}

# Function: Check if port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

# Function: Wait for port to be ready
wait_for_port() {
    local port=$1
    local service=$2
    local max_wait=30
    local count=0
    
    while [ $count -lt $max_wait ]; do
        if check_port $port; then
            return 0
        fi
        sleep 1
        count=$((count + 1))
    done
    
    print_message "$RED" "✗ $service 启动超时（端口 $port 未响应）"
    return 1
}

# Function: Start API service
start_api() {
    print_message "$YELLOW" "=== 启动 API Service ==="
    
    # Stop existing process if running
    if is_running "$API_PID_FILE" || check_port 7001; then
        print_message "$YELLOW" "检测到 API Service 已在运行，先停止..."
        stop_service "API Service" "$API_PID_FILE"
        lsof -ti:7001 | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
    
    cd "$API_DIR"
    
    # Check if .env exists
    if [ ! -f ".env" ]; then
        print_message "$RED" "✗ 未找到 api-service/.env 文件"
        return 1
    fi
    
    # Check if requirements are installed
    if ! python3 -c "import fastapi" 2>/dev/null; then
        print_message "$YELLOW" "安装 API 依赖..."
        pip3 install -r requirements.txt
    fi
    
    print_message "$YELLOW" "启动 API Service (端口 7001)..."
    nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 7001 > "$API_LOG" 2>&1 &
    echo $! > "$API_PID_FILE"
    
    # Wait for service to start
    if wait_for_port 7001 "API Service"; then
        print_message "$GREEN" "✓ API Service 启动成功 (PID: $(cat $API_PID_FILE))"
        print_message "$GREEN" "  - URL: http://localhost:7001"
        print_message "$GREEN" "  - Docs: http://localhost:7001/docs"
        print_message "$GREEN" "  - Log: $API_LOG"
        return 0
    else
        print_message "$RED" "✗ API Service 启动失败，请查看日志: $API_LOG"
        cat "$API_LOG"
        return 1
    fi
}

# Function: Start frontend
start_frontend() {
    print_message "$YELLOW" "=== 启动 Frontend ==="
    
    # Stop existing process if running
    if is_running "$FRONTEND_PID_FILE" || check_port 5173; then
        print_message "$YELLOW" "检测到 Frontend 已在运行，先停止..."
        stop_service "Frontend" "$FRONTEND_PID_FILE"
        lsof -ti:5173 | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
    
    cd "$FRONTEND_DIR"
    
    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        print_message "$YELLOW" "安装 Frontend 依赖..."
        npm install
    fi
    
    print_message "$YELLOW" "启动 Frontend (端口 5173)..."
    nohup npm run dev:h5 > "$FRONTEND_LOG" 2>&1 &
    echo $! > "$FRONTEND_PID_FILE"
    
    # Wait for service to start
    if wait_for_port 5173 "Frontend"; then
        print_message "$GREEN" "✓ Frontend 启动成功 (PID: $(cat $FRONTEND_PID_FILE))"
        print_message "$GREEN" "  - URL: http://localhost:5173"
        print_message "$GREEN" "  - Log: $FRONTEND_LOG"
        return 0
    else
        print_message "$RED" "✗ Frontend 启动失败，请查看日志: $FRONTEND_LOG"
        cat "$FRONTEND_LOG"
        return 1
    fi
}

# Function: Show status
show_status() {
    print_message "$YELLOW" "=== 服务状态 ==="
    
    if is_running "$API_PID_FILE"; then
        print_message "$GREEN" "✓ API Service: 运行中 (PID: $(cat $API_PID_FILE), 端口 7001)"
    else
        print_message "$RED" "✗ API Service: 未运行"
    fi
    
    if is_running "$FRONTEND_PID_FILE"; then
        print_message "$GREEN" "✓ Frontend: 运行中 (PID: $(cat $FRONTEND_PID_FILE), 端口 5173)"
    else
        print_message "$RED" "✗ Frontend: 未运行"
    fi
}


# Main script
main() {
    cd "$PROJECT_ROOT"
    
    case "${1:-}" in
        --stop)
            stop_all
            ;;
        --status)
            show_status
            ;;
        --restart)
            stop_all
            sleep 2
            main
            ;;
        *)
            print_message "$GREEN" "========================================="
            print_message "$GREEN" "  Football Betting System - 本地启动"
            print_message "$GREEN" "========================================="
            echo ""
            
            # Start services
            if start_api && start_frontend; then
                echo ""
                print_message "$GREEN" "========================================="
                print_message "$GREEN" "  所有服务启动成功！"
                print_message "$GREEN" "========================================="
                echo ""
                show_status
                echo ""
                print_message "$YELLOW" "提示:"
                print_message "$YELLOW" "  - 查看状态: ./start-local.sh --status"
                print_message "$YELLOW" "  - 停止服务: ./start-local.sh --stop"
                print_message "$YELLOW" "  - 重启服务: ./start-local.sh --restart"
                print_message "$YELLOW" "  - API 日志: tail -f $API_LOG"
                print_message "$YELLOW" "  - Frontend 日志: tail -f $FRONTEND_LOG"
            else
                print_message "$RED" "服务启动失败，请检查日志"
                exit 1
            fi
            ;;
    esac
}

# Handle Ctrl+C
trap 'print_message "$YELLOW" "\n中断操作"; exit 130' INT

main "$@"
