#!/bin/bash
"""
手机游戏舆情监控系统 - 启动脚本
用法: bash startup.sh [start|stop|restart|status]

所有服务:
  1. sentiment_service_ernie.py  (端口 8001) - 情感分析
  2. predict_service.py          (端口 5000) - 趋势预测
  3. UnifiedDataCleaner (Spark)  (内嵌)      - 数据清洗
  4. backend.jar                 (端口 8080) - Spring Boot
  5. frontend (nginx/vue)        (端口 5173) - 前端
"""

BASE_DIR=$(cd "$(dirname "$0")" && pwd)
LOG_DIR="$BASE_DIR/logs"
mkdir -p "$LOG_DIR"

PID_FILE="$BASE_DIR/.service_pids"

SERVICES=(
    "情感分析:sentiment_service_ernie.py:8001:python3"
    "趋势预测:predict_service.py:5000:python3"
    "后端:backend.jar:8080:java"
)

get_pid() {
    local port=$1
    if command -v ss &> /dev/null; then
        ss -tlnp 2>/dev/null | grep ":$port " | grep -oP 'pid=\K[0-9]+' | head -1
    elif command -v netstat &> /dev/null; then
        netstat -tlnp 2>/dev/null | grep ":$port " | grep -oP '[0-9]+/java|[0-9]+/python' | grep -oP '[0-9]+' | head -1
    else
        echo ""
    fi
}

start_service() {
    local name=$1
    local script=$2
    local port=$3
    local runner=$4

    local existing_pid=$(get_pid $port)
    if [ -n "$existing_pid" ]; then
        echo "[$name] 已运行 (PID: $existing_pid)"
        return
    fi

    echo "[$name] 启动中..."
    case $runner in
        python3)
            cd "$BASE_DIR"
            nohup python3 "$BASE_DIR/$script" --port "$port" >> "$LOG_DIR/${script%.py}.log" 2>&1 &
            echo $! >> "$PID_FILE"
            ;;
        java)
            cd "$BASE_DIR"
            nohup java -jar "$BASE_DIR/$script" --server.port="$port" >> "$LOG_DIR/backend.log" 2>&1 &
            echo $! >> "$PID_FILE"
            ;;
    esac
    sleep 2
    echo "[$name] 启动完成"
}

stop_service() {
    local name=$1
    local port=$2
    local pid=$(get_pid $port)
    if [ -n "$pid" ]; then
        echo "[$name] 停止中 (PID: $pid)..."
        kill $pid 2>/dev/null
        sleep 1
        if kill -0 $pid 2>/dev/null; then
            kill -9 $pid 2>/dev/null
        fi
        echo "[$name] 已停止"
    else
        echo "[$name] 未运行"
    fi
}

check_service() {
    local name=$1
    local port=$2
    local pid=$(get_pid $port)
    if [ -n "$pid" ]; then
        echo "  [$name] 运行中 (PID: $pid, 端口: $port)"
        return 0
    else
        echo "  [$name] 已停止 (端口: $port)"
        return 1
    fi
}

case "${1:-status}" in
    start)
        echo "启动所有服务..."
        > "$PID_FILE"
        for svc in "${SERVICES[@]}"; do
            IFS=':' read -r name script port runner <<< "$svc"
            start_service "$name" "$script" "$port" "$runner"
        done
        echo ""
        echo "=== 启动完成 ==="
        echo "情感分析: http://localhost:8001/health"
        echo "趋势预测: http://localhost:5000/health"
        echo "后端API:  http://localhost:8080/api/opinion/health"
        echo "前端:     http://localhost:5173"
        echo "日志目录: $LOG_DIR"
        ;;

    stop)
        echo "停止所有服务..."
        for svc in "${SERVICES[@]}"; do
            IFS=':' read -r name script port runner <<< "$svc"
            stop_service "$name" "$port"
        done
        echo "所有服务已停止"
        ;;

    restart)
        bash "$0" stop
        sleep 2
        bash "$0" start
        ;;

    status)
        echo "服务状态:"
        for svc in "${SERVICES[@]}"; do
            IFS=':' read -r name script port runner <<< "$svc"
            check_service "$name" "$port"
        done

        echo ""
        echo "检查 Python 预测服务:"
        if command -v curl &> /dev/null; then
            for port in 8001 5000; do
                resp=$(curl -s http://localhost:$port/health 2>/dev/null)
                if [ -n "$resp" ]; then
                    echo "  端口 $port: 响应正常 ($resp)"
                else
                    echo "  端口 $port: 无响应"
                fi
            done
        fi
        ;;

    *)
        echo "用法: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
