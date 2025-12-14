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
# 1. 初始化与日志
# -------------------------------
# 隐藏 httpx 库的轮询日志
logging.getLogger("httpx").setLevel(logging.WARNING)

# 隐藏 apscheduler 的 Job 执行日志
logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)

# 配置主程序日志格式和级别
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------------------
# 2. 统一配置加载逻辑
# -------------------------------
CONFIG_FILE = "config.json"

# 全局配置变量
BOT_TOKEN = None
OWNER_ID = None
PROXY_URL = None
DESTINATIONS = []
HB_FILE = None        # 心跳文件名
HB_INTERVAL = None    # 心跳间隔 (秒)
SILENT_FORWARDING = False # 全局静默转发标志

def load_config():
    # 从 config.json 加载所有配置
    global BOT_TOKEN, OWNER_ID, PROXY_URL, DESTINATIONS, HB_FILE, HB_INTERVAL, SILENT_FORWARDING
    
    logger.info(f"📋 正在加载配置文件: {CONFIG_FILE}...")

    if not os.path.exists(CONFIG_FILE):
        logger.critical(f"⛔ 找不到配置文件: {CONFIG_FILE}。程序将退出。")
        sys.exit(1)

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 加载 bot 部分配置
        bot_config = config.get("bot", {})
        BOT_TOKEN = bot_config.get("token")
        OWNER_ID = bot_config.get("owner_id")
        PROXY_URL = bot_config.get("proxy_url")
        SILENT_FORWARDING = bot_config.get("silent_forwarding", False)
        
        # 加载 watchdog 部分配置
        watchdog_config = config.get("watchdog", {})
        HB_FILE = watchdog_config.get("heartbeat_file")
        HB_INTERVAL = watchdog_config.get("heartbeat_interval_s")

        # 加载 destinations 部分配置
        DESTINATIONS = config.get("destinations", [])

        # 校验关键配置
        if not BOT_TOKEN or not OWNER_ID:
            logger.critical("⛔ 未配置 BOT_TOKEN 或 OWNER_ID。程序将退出。")
            sys.exit(1)

        if not isinstance(OWNER_ID, int):
            try:
                OWNER_ID = int(OWNER_ID)
            except ValueError:
                logger.critical("⛔ 'owner_id' 必须是数字。程序将退出。")
                sys.exit(1)

        # 日志输出更新
        logger.info(f"✅ 配置加载成功。Owner ID: {OWNER_ID}")
        logger.info(f"✅ 已加载 {len(DESTINATIONS)} 个转发目标规则。")

        if PROXY_URL:
            logger.info(f"🌐 代理已配置: {PROXY_URL}")
        if SILENT_FORWARDING:
             logger.info("🔇 全局静默转发已启用。")
        if HB_FILE and HB_INTERVAL:
            logger.info(f"❤️ 心跳配置：文件 {HB_FILE}，间隔 {HB_INTERVAL}s。")

    except json.JSONDecodeError as e:
        logger.critical(f"⛔ 配置文件 {CONFIG_FILE} 格式错误 (JSON 语法错误): {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"⛔ 加载配置文件时发生未知错误: {e}")
        sys.exit(1)

# 执行加载
load_config()

# MediaGroup 缓存
MEDIA_GROUP_CACHE = {}

# -------------------------------
# 3. 任务: 心跳 (Heartbeat)
# -------------------------------

async def heartbeat_task(context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """周期性地更新心跳文件一次，供看门狗监控"""
    if not HB_FILE:
        return

    try:
        with open(HB_FILE, 'w') as f:
            f.write(str(time.time()))
    except Exception as e:
        logger.error(f"❌ 周期性写入心跳文件失败: {e}")


# -------------------------------
# 4. 核心转发逻辑
# -------------------------------

async def forward_to_destinations(context: telegram.ext.ContextTypes.DEFAULT_TYPE, message=None, media_list=None):
    """核心分发函数：根据配置列表转发消息或媒体组。"""

    # 定义发送动作的内部函数
    async def send_action(chat_id, thread_id=None, is_silent=False): 
        target_str = f"{chat_id}" + (f" (Topic {thread_id})" if thread_id else "")

        try:
            if not chat_id:
                logger.error("❌ 目标配置缺少 'chat_id'，跳过此目标。")
                return

            params = {
                "chat_id": chat_id,
                "message_thread_id": thread_id,
                "disable_notification": is_silent # 应用静默标志
            }

            # 设置单独的发送超时，防止发图时卡死
            if media_list:
                # 发送相册，使用更长的媒体写入超时
                await context.bot.send_media_group(
                    media=media_list, 
                    media_write_timeout=60,
                    **params
                )
            elif message:
                # 转发单条
                await message.copy(
                    write_timeout=30,
                    **params
                )
        
        # 异常捕获块
        except httpx.RemoteProtocolError as e:
            logger.critical(f"❌ 转发到 {target_str} 时发生连接错误 (RemoteProtocolError)。该目标可能暂时不可达或网络中断。错误信息: {e}")
        except telegram.error.TelegramError as e:
            logger.error(f"❌ 转发到 {target_str} 失败 (Telegram API Error): {e}")
        except Exception as e:
            logger.error(f"❌ 转发到 {target_str} 失败 (Unknown Error): {e}")


    # 遍历统一的目标列表
    for dest in DESTINATIONS:
        chat_id = dest.get('chat_id')
        topic_ids = dest.get('topic_ids', [])

        # 确定此目标的静默状态 (目标配置优先于全局配置)
        is_silent_dest = dest.get('silent_forwarding', SILENT_FORWARDING) 
        
        # 话题判断逻辑
        target_threads = topic_ids if topic_ids else [None]

        # 对目标群组的每个话题（或主线程 None）执行发送
        for thread_id in target_threads:
            await send_action(chat_id, thread_id=thread_id, is_silent=is_silent_dest)


# -------------------------------
# 5. 业务逻辑
# -------------------------------
async def process_media_group(context: telegram.ext.ContextTypes.DEFAULT_TYPE, media_group_id: str):
    """处理并转发媒体组 (相册)"""
    # 延迟 2 秒，等待媒体组内的所有消息都到达
    await asyncio.sleep(2)

    if media_group_id not in MEDIA_GROUP_CACHE:
        return

    # 提取并清理缓存
    messages = MEDIA_GROUP_CACHE.pop(media_group_id)
    # 按照消息 ID 排序，确保相册顺序
    messages.sort(key=lambda x: x.message_id)

    media_list = []
    for msg in messages:
        caption = msg.caption
        entities = msg.caption_entities
        
        # 统一处理各种媒体类型
        if msg.photo:
            media_list.append(telegram.InputMediaPhoto(msg.photo[-1].file_id, caption=caption, caption_entities=entities))
        elif msg.video:
            media_list.append(telegram.InputMediaVideo(msg.video.file_id, caption=caption, caption_entities=entities))
        elif msg.audio:
            media_list.append(telegram.InputMediaAudio(msg.audio.file_id, caption=caption, caption_entities=entities))
        elif msg.document:
            media_list.append(telegram.InputMediaDocument(msg.document.file_id, caption=caption, caption_entities=entities))

    if media_list:
        logger.info(f"📤 正在转发相册 (共 {len(media_list)} 个文件)")
        await forward_to_destinations(context, media_list=media_list)


async def handler(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """主消息处理器：负责过滤消息并分发给转发函数"""
    msg = update.message

    # 1. 消息过滤: 必须是私聊，且必须来自 OWNER_ID
    if not msg or msg.chat.type != "private" or msg.from_user.id != OWNER_ID:
        return
    # 2. 忽略命令
    if msg.text and msg.text.startswith("/"):
        return

    # 3. 媒体组 (相册) 处理逻辑
    if msg.media_group_id:
        is_first = msg.media_group_id not in MEDIA_GROUP_CACHE

        if is_first:
            MEDIA_GROUP_CACHE[msg.media_group_id] = []

        MEDIA_GROUP_CACHE[msg.media_group_id].append(msg)

        if is_first:
            # 首次接收媒体组消息时，创建延迟处理任务
            context.application.create_task(process_media_group(context, msg.media_group_id))
        return

    # 4. 单条消息处理
    logger.info(f"📤 正在转发单条消息 (ID: {msg.message_id})")
    await forward_to_destinations(context, message=msg)


# -----------------------------
# 主程序
# -----------------------------
def main():
    try:
        # 配置 HTTPXRequest，设置明确的超时时间，解决卡死问题
        request_config = telegram.request.HTTPXRequest(
            connection_pool_size=8,
            read_timeout=30.0,    # 30秒无数据则判定断开并触发重连
            connect_timeout=20.0, # 20秒连接建立超时
            write_timeout=30.0,   # 30秒普通消息写入超时
            media_write_timeout=60.0 # 60秒媒体文件写入超时
        )

        # 构建 Application
        builder = telegram.ext.ApplicationBuilder().token(BOT_TOKEN).request(request_config)

        # 代理配置
        if PROXY_URL and PROXY_URL.strip():
            builder.proxy_url(PROXY_URL)

        app = builder.build()
        app.add_handler(telegram.ext.MessageHandler(telegram.ext.filters.ChatType.PRIVATE, handler))
        
        # 心跳逻辑配置
        if HB_FILE and HB_INTERVAL:
            logger.info("❤️ 正在创建初始心跳文件...")
            try:
                with open(HB_FILE, 'w') as f:
                    f.write(str(time.time()))
            except Exception as e:
                logger.error(f"❌ 首次写入心跳文件失败，请检查文件权限: {e}")

            # 启动周期性心跳任务
            app.job_queue.run_repeating(
                heartbeat_task,  
                interval=HB_INTERVAL
            )
            logger.info(f"✅ 心跳任务已启动，间隔: {HB_INTERVAL}s。")
        else:
            logger.warning("⚠️ 心跳功能已禁用 (缺少配置)。")

        logger.info("🚀 机器人已启动，开始轮询监听...")

        # 启动轮询，设置轮询超时时间
        app.run_polling(
            allowed_updates=telegram.Update.ALL_TYPES, 
            close_loop=False,
            timeout=30 # 客户端等待服务器响应的最大时间（也是长轮询的周期）
        )

    except KeyboardInterrupt:
        logger.info("👋 机器人接收到 Ctrl+C，正常关闭。")
        # 退出时清理心跳文件
        if HB_FILE and os.path.exists(HB_FILE):
            os.remove(HB_FILE)
        sys.exit(0)
    except Exception as e:
        logger.critical(f"🔥 发生未捕获的严重错误，程序崩溃: {e}", exc_info=True)
        # 异常退出时清理心跳文件
        if HB_FILE and os.path.exists(HB_FILE):
            os.remove(HB_FILE)
        sys.exit(1)


if __name__ == "__main__":
    main()