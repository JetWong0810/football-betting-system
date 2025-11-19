#!/bin/bash

###############################################################################
# 部署脚本测试工具
# 
# 用于测试各种部署方式，不实际执行部署
# 使用：./test_deploy.sh
###############################################################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

# 测试脚本语法
test_syntax() {
    print_test "测试脚本语法..."
    if bash -n deploy.sh 2>&1; then
        print_success "脚本语法正确"
        return 0
    else
        print_error "脚本语法错误"
        return 1
    fi
}

# 测试参数解析
test_args() {
    print_test "测试参数解析..."
    
    local errors=0
    
    # 测试 --help
    if ./deploy.sh --help 2>&1 | grep -q "用法:"; then
        print_success "--help 参数正常"
    else
        print_error "--help 参数异常"
        errors=$((errors + 1))
    fi
    
    # 测试 --api-only
    if ./deploy.sh --api-only --help 2>&1 | grep -q "用法:"; then
        print_success "--api-only 参数正常"
    else
        print_error "--api-only 参数异常"
        errors=$((errors + 1))
    fi
    
    # 测试 --branch
    if ./deploy.sh --branch test --help 2>&1 | grep -q "用法:"; then
        print_success "--branch 参数正常"
    else
        print_error "--branch 参数异常"
        errors=$((errors + 1))
    fi
    
    # 测试无效参数
    if ./deploy.sh --invalid-param 2>&1 | grep -q "未知选项"; then
        print_success "无效参数检测正常"
    else
        print_error "无效参数检测异常"
        errors=$((errors + 1))
    fi
    
    if [ $errors -eq 0 ]; then
        print_success "参数解析测试通过"
        return 0
    else
        print_error "参数解析测试失败 ($errors 个错误)"
        return 1
    fi
}

# 测试 Git 仓库检测
test_git_detection() {
    print_test "测试 Git 仓库自动检测..."
    
    if [ -d ".git" ]; then
        local repo_url=$(git remote get-url origin 2>/dev/null || echo "")
        if [ -n "$repo_url" ]; then
            print_success "Git 仓库检测正常: $repo_url"
            return 0
        else
            print_info "Git 仓库存在但未配置远程地址"
            return 0
        fi
    else
        print_info "当前目录不是 Git 仓库"
        return 0
    fi
}

# 测试函数定义
test_functions() {
    print_test "测试函数定义..."
    
    local errors=0
    
    # 检查关键函数是否存在
    local functions=("get_repo_url" "check_ssh" "deploy_api" "deploy_scraper" "deploy_frontend")
    
    for func in "${functions[@]}"; do
        if grep -q "^$func()" deploy.sh; then
            print_success "函数 $func 已定义"
        else
            print_error "函数 $func 未定义"
            errors=$((errors + 1))
        fi
    done
    
    if [ $errors -eq 0 ]; then
        print_success "函数定义测试通过"
        return 0
    else
        print_error "函数定义测试失败 ($errors 个错误)"
        return 1
    fi
}

# 测试 SSH heredoc 语法
test_heredoc() {
    print_test "测试 SSH heredoc 语法..."
    
    # 检查是否有未转义的变量问题
    local errors=0
    
    # 检查 GITEOF 是否正确关闭
    if grep -c "<< GITEOF" deploy.sh | grep -q "^2$"; then
        print_success "GITEOF heredoc 配对正确"
    else
        print_error "GITEOF heredoc 配对可能有问题"
        errors=$((errors + 1))
    fi
    
    # 检查是否有在远程执行的本地函数调用
    if grep -A 5 "<< GITEOF" deploy.sh | grep -q "print_"; then
        print_error "发现 heredoc 中使用了本地函数（应该使用 echo）"
        errors=$((errors + 1))
    else
        print_success "heredoc 中未使用本地函数"
    fi
    
    if [ $errors -eq 0 ]; then
        print_success "heredoc 语法测试通过"
        return 0
    else
        print_error "heredoc 语法测试失败 ($errors 个错误)"
        return 1
    fi
}

# 测试变量使用
test_variables() {
    print_test "测试变量使用..."
    
    local errors=0
    
    # 检查关键变量是否定义
    local vars=("GUIYUN_HOST" "MYSQL_BACKUP_HOST" "PROJECT_DIR" "GIT_BRANCH")
    
    for var in "${vars[@]}"; do
        if grep -q "^$var=" deploy.sh; then
            print_success "变量 $var 已定义"
        else
            print_error "变量 $var 未定义"
            errors=$((errors + 1))
        fi
    done
    
    if [ $errors -eq 0 ]; then
        print_success "变量使用测试通过"
        return 0
    else
        print_error "变量使用测试失败 ($errors 个错误)"
        return 1
    fi
}

# 主测试函数
main() {
    echo ""
    echo "=========================================="
    echo "  部署脚本测试工具"
    echo "=========================================="
    echo ""
    
    local total=0
    local passed=0
    local failed=0
    
    # 运行所有测试
    tests=(
        "test_syntax:语法检查"
        "test_args:参数解析"
        "test_git_detection:Git 检测"
        "test_functions:函数定义"
        "test_heredoc:heredoc 语法"
        "test_variables:变量使用"
    )
    
    for test_info in "${tests[@]}"; do
        IFS=':' read -r test_func test_name <<< "$test_info"
        total=$((total + 1))
        
        echo ""
        print_info "测试 $total/${#tests[@]}: $test_name"
        
        if $test_func; then
            passed=$((passed + 1))
        else
            failed=$((failed + 1))
        fi
    done
    
    # 总结
    echo ""
    echo "=========================================="
    echo "  测试结果"
    echo "=========================================="
    echo ""
    echo "总测试数: $total"
    echo -e "${GREEN}通过: $passed${NC}"
    if [ $failed -gt 0 ]; then
        echo -e "${RED}失败: $failed${NC}"
    else
        echo -e "${GREEN}失败: $failed${NC}"
    fi
    echo ""
    
    if [ $failed -eq 0 ]; then
        print_success "所有测试通过！✓"
        return 0
    else
        print_error "有 $failed 个测试失败"
        return 1
    fi
}

# 运行测试
main

