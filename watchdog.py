import subprocess
import sys
import time
import logging
import os
import json
import psutil  # 新增：用于深度清理进程树

# -----------------------------------------
#              看门狗配置
# -----------------------------------------
BOT_SCRIPT = "main.py"
CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "HB_FILE": "bot.heartbeat",
    "RESTART_DELAY": 5,
    "HB_TIMEOUT": 300,
    "MAX_RESTARTS": 5
}

logging.basicConfig(
    format="%(asctime)s - [WATCHDOG] - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("Watchdog")

def load_watchdog_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        wc = config.get("watchdog", {})
        return {
            "HB_FILE": wc.get("heartbeat_file", DEFAULT_CONFIG["HB_FILE"]),
            "RESTART_DELAY": wc.get("restart_delay_s", DEFAULT_CONFIG["RESTART_DELAY"]),
            "HB_TIMEOUT": wc.get("heartbeat_timeout_s", DEFAULT_CONFIG["HB_TIMEOUT"]),
            "MAX_RESTARTS": wc.get("max_consecutive_restarts", DEFAULT_CONFIG["MAX_RESTARTS"])
        }
    except:
        return DEFAULT_CONFIG

# 初始化配置
CONF = load_watchdog_config()

def kill_process_tree(pid):
    """【核心改进】彻底清理进程及其所有子进程"""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            logger.warning(f"正在强制终止子进程: {child.pid}")
            child.kill() # 发送 SIGKILL
        logger.warning(f"正在强制终止主进程: {parent.pid}")
        parent.kill()
    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        logger.error(f"清理进程树时发生错误: {e}")

def cleanup_environment():
    """重启前的物理清理"""
    if os.path.exists(CONF["HB_FILE"]):
        try:
            os.remove(CONF["HB_FILE"])
            logger.info("🗑️ 已清理过期心跳文件。")
        except: pass

def is_heartbeat_alive():
    if not os.path.exists(CONF["HB_FILE"]):
        return True # 文件不存在时不立即判定死亡，等待下次检查
    try:
        last_update = os.path.getmtime(CONF["HB_FILE"])
        if (time.time() - last_update) > CONF["HB_TIMEOUT"]:
            return False
        return True
    except:
        return False

def start_bot():
    logger.info(f"🤖 看门狗启动，监控: {BOT_SCRIPT}")
    consecutive_failures = 0
    
    while True:
        if consecutive_failures >= CONF["MAX_RESTARTS"]:
            logger.critical("❌ 连续失败次数过多，看门狗停止。")
            sys.exit(1)

        cleanup_environment()
        logger.info(f"🚀 正在启动机器人... (失败计数: {consecutive_failures})")
        
        # 启动子进程
        process = subprocess.Popen([sys.executable, BOT_SCRIPT])
        
        try:
            while process.poll() is None:
                time.sleep(15) # 每15秒检查一次心跳
                
                if not is_heartbeat_alive():
                    logger.critical(f"🔥 检测到心跳超时 (> {CONF['HB_TIMEOUT']}s)！")
                    kill_process_tree(process.pid) # 彻底杀掉
                    consecutive_failures += 1
                    break
            
            # 进程退出后的处理
            if process.returncode is not None:
                if process.returncode == 0:
                    logger.info("✅ 机器人正常退出。")
                    break
                else:
                    logger.error(f"🚨 机器人异常退出 (码: {process.returncode})")
                    consecutive_failures += 1
                    
            logger.info(f"⏳ {CONF['RESTART_DELAY']}秒后彻底重启...")
            time.sleep(CONF["RESTART_DELAY"])

        except KeyboardInterrupt:
            logger.info("🛑 收到指令，正在关闭...")
            kill_process_tree(process.pid)
            sys.exit(0)

if __name__ == "__main__":
    start_bot()