import logging
import asyncio
import os
import json
import sys
import time
import telegram 
import telegram.ext 
import httpx 
import telegram.request

# -------------------------------
# 1. 统一配置常量和全局变量
# -------------------------------
CONFIG_FILE = "config.json"

# 全局配置变量 (由 load_config() 填充)
BOT_TOKEN = None
OWNER_ID = None
PROXY_URL = None
DESTINATIONS = []
HB_FILE = None        
HB_INTERVAL = None    
SILENT_FORWARDING = False 

# 新增：日志和网络配置变量
LOG_LEVEL = "INFO"
READ_TIMEOUT = 20.0    
CONNECT_TIMEOUT = 10.0
POOL_TIMEOUT = 10.0
WRITE_TIMEOUT = 20.0
MEDIA_WRITE_TIMEOUT = 60.0
POOL_SIZE = 2048

# 用于缓存媒体组（相册）消息的字典
MEDIA_GROUP_CACHE = {} 


def load_config():
    """从 config.json 加载所有配置，并填充全局变量。"""
    global BOT_TOKEN, OWNER_ID, PROXY_URL, DESTINATIONS
    global HB_FILE, HB_INTERVAL, SILENT_FORWARDING
    global LOG_LEVEL, READ_TIMEOUT, CONNECT_TIMEOUT, POOL_TIMEOUT
    global WRITE_TIMEOUT, MEDIA_WRITE_TIMEOUT, POOL_SIZE
    
    logger.info(f"正在加载配置文件: {CONFIG_FILE}...")

    if not os.path.exists(CONFIG_FILE):
        logger.critical(f"找不到配置文件: {CONFIG_FILE}。程序将退出。")
        sys.exit(1)

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 加载机器人主体配置 (包含日志级别)
        bot_config = config.get("bot", {})
        BOT_TOKEN = bot_config.get("token")
        OWNER_ID = bot_config.get("owner_id")
        PROXY_URL = bot_config.get("proxy_url")
        SILENT_FORWARDING = bot_config.get("silent_forwarding", False)
        LOG_LEVEL = bot_config.get("log_level", "INFO").upper()
        
        # 加载看门狗相关配置
        watchdog_config = config.get("watchdog", {})
        HB_FILE = watchdog_config.get("heartbeat_file")
        HB_INTERVAL = watchdog_config.get("heartbeat_interval_s")

        # 加载网络配置 (NEW)
        network_config = config.get("network", {})
        READ_TIMEOUT = network_config.get("read_timeout", 20.0)    
        CONNECT_TIMEOUT = network_config.get("connect_timeout", 10.0) 
        POOL_TIMEOUT = network_config.get("pool_timeout", 10.0)
        WRITE_TIMEOUT = network_config.get("write_timeout", 20.0)
        MEDIA_WRITE_TIMEOUT = network_config.get("media_write_timeout", 60.0)
        POOL_SIZE = network_config.get("connection_pool_size", 2048)

        # 加载转发目标列表配置
        DESTINATIONS = config.get("destinations", [])

        # 校验关键配置
        if not BOT_TOKEN or not OWNER_ID:
            logger.critical("未配置 BOT_TOKEN 或 OWNER_ID。程序将退出。")
            sys.exit(1)

        # 确保 OWNER_ID 是整数类型
        if not isinstance(OWNER_ID, int):
            try:
                OWNER_ID = int(OWNER_ID)
            except ValueError:
                logger.critical("'owner_id' 必须是数字。程序将退出。")
                sys.exit(1)

        logger.info(f"配置加载成功。Owner ID: {OWNER_ID}")
        logger.info(f"已加载 {len(DESTINATIONS)} 个转发目标规则。")
        logger.info(f"日志级别: {LOG_LEVEL} | 连接超时: {CONNECT_TIMEOUT}s | 读取超时: {READ_TIMEOUT}s")

    except Exception as e:
        logger.critical(f"加载配置文件时发生错误: {e}")
        sys.exit(1)


# -------------------------------
# 2. 初始化日志 (动态设置)
# -------------------------------
# 隐藏底层库如 httpx, httpcore, apscheduler 的调试日志，防止刷屏
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)

# 初始化 logger 实例，level 在 main() 中动态配置
logger = logging.getLogger(__name__)

# -------------------------------
# 3. 任务: 心跳 (Heartbeat) - 周期性任务
# -------------------------------
async def heartbeat_task(context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """周期性地更新心跳文件，证明事件循环正在运行（防止空闲超时）。"""
    if not HB_FILE or not HB_INTERVAL:
        return
    try:
        with open(HB_FILE, 'w') as f:
            f.write(str(time.time()))
    except Exception as e:
        logger.error(f"周期性写入心跳文件失败: {e}")

# -------------------------------
# 4. 任务: 错误处理 (强制退出)
# -------------------------------
async def error_handler(update: object, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """
    全局错误处理器。当检测到网络超时等严重错误时，强制退出进程以触发看门狗重启。
    """
    logger.error(f"发生未捕获异常: {context.error}")
    
    # 检查是否为 httpx 相关的连接或读取超时
    if isinstance(context.error, (httpx.ConnectTimeout, httpx.ReadTimeout)):
        logger.critical("检测到连接或读取超时，强制退出以触发看门狗重启...")
        # 强制终止整个进程，避免 asyncio 挂起
        os._exit(1)

# -------------------------------
# 5. 核心转发逻辑
# -------------------------------
async def forward_to_destinations(context: telegram.ext.ContextTypes.DEFAULT_TYPE, message=None, media_list=None):
    """根据目标列表转发消息或媒体组。"""
    # 内部函数：执行实际的发送操作
    async def send_action(chat_id, thread_id=None, is_silent=False):
        target_str = f"{chat_id}" + (f" (Topic {thread_id})" if thread_id else "")
        try:
            if not chat_id: return

            params = {
                "chat_id": chat_id,
                "message_thread_id": thread_id,
                "disable_notification": is_silent # 控制消息是否静默通知
            }

            if media_list:
                # 发送媒体组（相册）
                await context.bot.send_media_group(media=media_list, **params)
            elif message:
                # 转发单条消息
                await message.copy(**params)
        
        except Exception as e:
            logger.error(f"转发到 {target_str} 失败: {e}")

    # 遍历所有目标配置
    for dest in DESTINATIONS:
        chat_id = dest.get('chat_id')
        topic_ids = dest.get('topic_ids', [])
        # 目标配置的静默状态优先于全局配置
        is_silent_dest = dest.get('silent_forwarding', SILENT_FORWARDING) 
        
        # 确定需要转发的话题ID列表 (包含 None 代表主线程)
        target_threads = topic_ids if topic_ids else [None]

        # 对每个话题执行发送
        for thread_id in target_threads:
            await send_action(chat_id, thread_id=thread_id, is_silent=is_silent_dest)

# -------------------------------
# 6. 业务逻辑
# -------------------------------
async def process_media_group(context: telegram.ext.ContextTypes.DEFAULT_TYPE, media_group_id: str):
    """处理并转发媒体组 (相册)"""
    # 延迟 2 秒等待相册完整接收
    await asyncio.sleep(2) 
    if media_group_id not in MEDIA_GROUP_CACHE: return

    # 提取并清理缓存
    messages = MEDIA_GROUP_CACHE.pop(media_group_id)
    # 确保相册消息按顺序排列
    messages.sort(key=lambda x: x.message_id)

    media_list = []
    for msg in messages:
        caption = msg.caption
        entities = msg.caption_entities
        # 根据消息类型创建 InputMedia 对象
        if msg.photo:
            media_list.append(telegram.InputMediaPhoto(msg.photo[-1].file_id, caption=caption, caption_entities=entities))
        elif msg.video:
            media_list.append(telegram.InputMediaVideo(msg.video.file_id, caption=caption, caption_entities=entities))
        elif msg.audio:
            media_list.append(telegram.InputMediaAudio(msg.audio.file_id, caption=caption, caption_entities=entities))
        elif msg.document:
            media_list.append(telegram.InputMediaDocument(msg.document.file_id, caption=caption, caption_entities=entities))

    if media_list:
        logger.info(f"正在转发相册 (共 {len(media_list)} 个文件)")
        await forward_to_destinations(context, media_list=media_list)

async def handler(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """主消息处理器：负责过滤消息并分发给转发函数"""
    msg = update.message
    # 过滤：必须是私聊，且必须来自预设的 OWNER_ID
    if not msg or msg.chat.type != "private" or msg.from_user.id != OWNER_ID: return
    # 忽略命令
    if msg.text and msg.text.startswith("/"): return

    # 媒体组 (相册) 消息处理逻辑
    if msg.media_group_id:
        is_first = msg.media_group_id not in MEDIA_GROUP_CACHE
        if is_first: MEDIA_GROUP_CACHE[msg.media_group_id] = []
        MEDIA_GROUP_CACHE[msg.media_group_id].append(msg)
        if is_first:
            # 首次接收时，创建延迟任务等待相册完整
            context.application.create_task(process_media_group(context, msg.media_group_id))
        return

    # 单条消息处理
    logger.info(f"正在转发单条消息 (ID: {msg.message_id})")
    await forward_to_destinations(context, message=msg)

# -----------------------------
# 主程序
# -----------------------------
def main():
    try:
        # 1. 在程序启动时加载所有配置
        load_config()

        # 2. 动态配置日志级别
        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            level=getattr(logging, LOG_LEVEL, logging.INFO) # 使用配置中的 LOG_LEVEL
        )
        # 重新获取 logger 实例以应用新级别
        global logger
        logger = logging.getLogger(__name__)

        # 3. 配置 HTTPX 客户端参数 (使用配置中的值，确保短超时)
        request_params = {
            "connection_pool_size": POOL_SIZE,
            "read_timeout": READ_TIMEOUT,    
            "connect_timeout": CONNECT_TIMEOUT, 
            "pool_timeout": POOL_TIMEOUT,       # 连接池获取超时
            "write_timeout": WRITE_TIMEOUT,   
            "media_write_timeout": MEDIA_WRITE_TIMEOUT 
        }
        
        # 4. 代理配置
        if PROXY_URL and PROXY_URL.strip():
            logger.info(f"代理已配置: {PROXY_URL}")
            request_params["proxy"] = PROXY_URL
        
        # 5. 创建 HTTP 请求配置对象
        request_config = telegram.request.HTTPXRequest(**request_params)

        # 6. 构建 Application
        builder = telegram.ext.ApplicationBuilder().token(BOT_TOKEN).request(request_config)
        app = builder.build()
        
        # 添加 Handler 和 Error Handler
        app.add_handler(telegram.ext.MessageHandler(telegram.ext.filters.ChatType.PRIVATE, handler))
        app.add_error_handler(error_handler) # 注册强制退出错误处理器
        
        # 7. 心跳任务配置 (恢复周期性任务)
        if HB_FILE and HB_INTERVAL:
            try:
                # 首次写入心跳文件，防止看门狗误判
                with open(HB_FILE, 'w') as f: f.write(str(time.time()))
            except Exception: pass
            
            # 启动周期性心跳任务（确保空闲时看门狗不超时）
            app.job_queue.run_repeating(heartbeat_task, interval=HB_INTERVAL)
        else:
            logger.warning("心跳功能已禁用 (缺少配置)。")

        logger.info(f"机器人已启动，正在监听...")
        
        # 8. 启动长轮询
        app.run_polling(allowed_updates=telegram.Update.ALL_TYPES, close_loop=False)

    except KeyboardInterrupt:
        logger.info("正常退出。")
        if HB_FILE and os.path.exists(HB_FILE): os.remove(HB_FILE)
        sys.exit(0)
    except Exception as e:
        logger.critical(f"程序崩溃: {e}", exc_info=True)
        if HB_FILE and os.path.exists(HB_FILE): os.remove(HB_FILE)
        sys.exit(1)


if __name__ == "__main__":
    main()