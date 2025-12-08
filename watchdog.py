import subprocess
import sys
import time
import logging
import os
import json 

# ==========================================
#              看门狗配置
# ==========================================
BOT_SCRIPT = "main.py"
CONFIG_FILE = "config.json"

# 默认值 (在 config.json 缺失或不完整时使用)
DEFAULT_CONFIG = {
    "HB_FILE": "bot.heartbeat",
    "RESTART_DELAY": 5,
    "HB_TIMEOUT": 300,
    "MAX_RESTARTS": 5
}

# 配置看门狗日志
logging.basicConfig(
    format="%(asctime)s - [WATCHDOG] - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("Watchdog")


def load_watchdog_config():
    """加载必要的配置并更新全局常量。"""
    
    if not os.path.exists(CONFIG_FILE):
        logger.warning(f"⚠️ 找不到配置文件 {CONFIG_FILE}，将使用默认看门狗参数。")
        return DEFAULT_CONFIG

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        watchdog_config = config.get("watchdog", {})
        
        # 从配置中加载值，如果缺失则使用默认值
        loaded_config = {
            "HB_FILE": watchdog_config.get("heartbeat_file", DEFAULT_CONFIG["HB_FILE"]),
            "RESTART_DELAY": watchdog_config.get("restart_delay_s", DEFAULT_CONFIG["RESTART_DELAY"]),
            "HB_TIMEOUT": watchdog_config.get("heartbeat_timeout_s", DEFAULT_CONFIG["HB_TIMEOUT"]),
            "MAX_RESTARTS": watchdog_config.get("max_consecutive_restarts", DEFAULT_CONFIG["MAX_RESTARTS"])
        }
        logger.info(f"✅ 看门狗参数已加载。超时: {loaded_config['HB_TIMEOUT']}s, 最大重启: {loaded_config['MAX_RESTARTS']}次。")
        return loaded_config

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"❌ 加载或解析配置文件时发生错误: {e}。将使用默认看门狗参数。")
        return DEFAULT_CONFIG

# 加载配置
LOADED_CONFIG = load_watchdog_config()

# 使用加载后的值定义常量
HEARTBEAT_FILE = LOADED_CONFIG["HB_FILE"]
RESTART_DELAY = LOADED_CONFIG["RESTART_DELAY"]
HEARTBEAT_TIMEOUT = LOADED_CONFIG["HB_TIMEOUT"]
MAX_CONSECUTIVE_RESTARTS = LOADED_CONFIG["MAX_RESTARTS"]
# ==========================================
#              看门狗配置 (结束)
# ==========================================


def is_heartbeat_alive():
    """检查心跳文件是否在 HEARTBEAT_TIMEOUT 时间内更新"""
    if not os.path.exists(HEARTBEAT_FILE):
        return False
        
    try:
        last_update = os.path.getmtime(HEARTBEAT_FILE)
        current_time = time.time()
        
        # 检查时间差
        if (current_time - last_update) > HEARTBEAT_TIMEOUT:
            return False
        return True
    except Exception as e:
        logger.error(f"❌ 检查心跳文件失败: {e}")
        return False


def start_bot_with_watchdog():
    """循环启动机器人子进程并监控心跳"""
    logger.info(f"🤖 看门狗已启动，监控脚本: {BOT_SCRIPT}")
    
    command = [sys.executable, BOT_SCRIPT]
    process = None
    consecutive_failures = 0
    
    while True:
        if process is None:
            # 检查是否达到重启限制
            if consecutive_failures >= MAX_CONSECUTIVE_RESTARTS:
                logger.critical(f"❌ 机器人连续失败次数达到 {MAX_CONSECUTIVE_RESTARTS} 次。为避免资源滥用，看门狗已停止运行。")
                if os.path.exists(HEARTBEAT_FILE):
                     os.remove(HEARTBEAT_FILE)
                sys.exit(1)
            
            # 启动机器人
            logger.info(f"🚀 正在启动机器人程序 ({BOT_SCRIPT})... (当前连续失败次数: {consecutive_failures})")
            process = subprocess.Popen(command)
        
        try:
            # 持续监控
            while process.poll() is None: 
                time.sleep(15) 

                if not is_heartbeat_alive():
                    # --- 1. 心跳超时，强制重启流程 ---
                    logger.critical(f"🔥 机器人心跳超时 (> {HEARTBEAT_TIMEOUT}s)，判定卡死，强制重启!")
                    
                    # 强制终止子进程
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    
                    # 递增失败计数，重置进程，并清除心跳文件
                    consecutive_failures += 1
                    process = None
                    if os.path.exists(HEARTBEAT_FILE):
                         os.remove(HEARTBEAT_FILE)
                         
                    break # 退出内部循环
                
            # --- 2. 退出监控循环后的检查 ---
            
            if process is None:
                # 如果 process 为 None，说明是上面心跳超时触发的重启
                logger.info(f"⏳ {RESTART_DELAY}秒后尝试自动重启...")
                time.sleep(RESTART_DELAY)
                continue
            
            # 如果程序执行到这里，说明子进程是自行退出的
            exit_code = process.returncode
            
            if exit_code == 0:
                # 正常退出：重置失败计数
                logger.info("✅ 机器人正常退出 (退出码 0)。看门狗停止监控。")
                consecutive_failures = 0
                break
            else:
                # 异常退出：递增失败计数
                logger.error(f"🚨 机器人异常退出 (退出码: {exit_code})。")
                consecutive_failures += 1
                process = None
                logger.info(f"⏳ {RESTART_DELAY}秒后尝试自动重启...")
                time.sleep(RESTART_DELAY)

        except KeyboardInterrupt:
            # 优雅退出 (用户按 Ctrl+C)
            logger.info("🛑 接收到停止指令 (Ctrl+C)，正在关闭机器人...")
            if process:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            if os.path.exists(HEARTBEAT_FILE):
                os.remove(HEARTBEAT_FILE)
            logger.info("看门狗正常退出。")
            sys.exit(0)
        except Exception as e:
            # 看门狗自身错误，等待后重试
            logger.critical(f"🚨 看门狗自身发生错误: {e}", exc_info=True)
            process = None
            consecutive_failures += 1 
            time.sleep(RESTART_DELAY)


if __name__ == "__main__":
    start_bot_with_watchdog()