import logging
import asyncio
import os
import json
import sys
import time
import telegram 
import telegram.ext 

# -------------------------------
# 1. 初始化与日志
# -------------------------------
# 1.1 隐藏 httpx 轮询日志
logging.getLogger("httpx").setLevel(logging.WARNING)

# 1.2 配置主程序日志格式和级别
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
HB_FILE = None        # Heartbeat File Name
HB_INTERVAL = None    # Heartbeat Interval (seconds)

def load_config():
    """从 config.json 加载所有配置"""
    global BOT_TOKEN, OWNER_ID, PROXY_URL, DESTINATIONS, HB_FILE, HB_INTERVAL
    
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

        logger.info(f"✅ 配置加载成功。Owner ID: {OWNER_ID}")
        logger.info(f"✅ 已加载 {len(DESTINATIONS)} 个转发目标规则。")
        
        if PROXY_URL:
            logger.info(f"🌐 代理已启用: {PROXY_URL}")
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
# 3. 任务: 心跳 (Heartbeat) - 修复 TypeError
# -------------------------------

# 必须是 async 函数，与 JobQueue 内部的 await 机制兼容
async def heartbeat_task(context: telegram.ext.ContextTypes.DEFAULT_TYPE): 
    """周期性地更新心跳文件一次，由 JobQueue 负责重复调用"""
    if not HB_FILE or not HB_INTERVAL:
         # 这是一个周期性任务，如果配置无效，只记录警告，但不返回或抛出
         return
         
    try:
        # 注意：此处不应使用 await，因为文件 I/O 是同步操作
        with open(HB_FILE, 'w') as f:
            f.write(str(time.time()))
    except Exception as e:
        logger.error(f"❌ 周期性写入心跳文件失败: {e}")


# -------------------------------
# 4. 核心转发逻辑
# -------------------------------

async def forward_to_destinations(context: telegram.ext.ContextTypes.DEFAULT_TYPE, message=None, media_list=None):
    """
    核心分发函数：根据 DESTINATIONS 列表转发消息或媒体组。
    """
    
    # 定义发送动作的内部函数
    async def send_action(chat_id, thread_id=None):
        try:
            if not chat_id:
                logger.error("❌ 目标配置缺少 'chat_id'，跳过此目标。")
                return

            if media_list:
                # 发送相册
                await context.bot.send_media_group(
                    chat_id=chat_id, 
                    message_thread_id=thread_id, 
                    media=media_list
                )
            elif message:
                # 转发单条
                await message.copy(
                    chat_id=chat_id, 
                    message_thread_id=thread_id
                )
        except Exception as e:
            target_str = f"{chat_id}" + (f" (Topic {thread_id})" if thread_id else "")
            logger.error(f"❌ 转发到 {target_str} 失败: {e}")

    # 遍历统一的目标列表
    for dest in DESTINATIONS:
        chat_id = dest.get('chat_id')
        topic_ids = dest.get('topic_ids', []) 

        target_threads = []

        # 话题判断逻辑
        if not topic_ids:
            target_threads = [None]
        else:
            target_threads = topic_ids

        # 对目标群组的每个话题（或主线程 None）执行发送
        for thread_id in target_threads:
            await send_action(chat_id, thread_id=thread_id)


# -------------------------------
# 5. 业务逻辑
# -------------------------------
async def process_media_group(context: telegram.ext.ContextTypes.DEFAULT_TYPE, media_group_id: str):
    await asyncio.sleep(2) 

    if media_group_id not in MEDIA_GROUP_CACHE:
        return
    
    messages = MEDIA_GROUP_CACHE.pop(media_group_id)
    messages.sort(key=lambda x: x.message_id)

    media_list = []
    for msg in messages:
        caption = msg.caption
        entities = msg.caption_entities
        
        # 使用 telegram.InputMediaXxx
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
    msg = update.message

    if not msg or msg.chat.type != "private" or msg.from_user.id != OWNER_ID:
        return
    if msg.text and msg.text.startswith("/"):
        return

    if msg.media_group_id:
        is_first = msg.media_group_id not in MEDIA_GROUP_CACHE
        
        if is_first:
            MEDIA_GROUP_CACHE[msg.media_group_id] = []
        
        MEDIA_GROUP_CACHE[msg.media_group_id].append(msg)

        if is_first:
            context.application.create_task(process_media_group(context, msg.media_group_id))
        return

    logger.info(f"📤 正在转发单条消息 (ID: {msg.message_id})")
    await forward_to_destinations(context, message=msg)


# -----------------------------
# 主程序
# -----------------------------
def main():
    try:
        # 使用 telegram.ext.ApplicationBuilder
        builder = telegram.ext.ApplicationBuilder().token(BOT_TOKEN)
        
        if PROXY_URL and PROXY_URL.strip():
            builder.proxy(PROXY_URL)

        app = builder.build()
        # 使用 telegram.ext.MessageHandler 和 telegram.ext.filters
        app.add_handler(telegram.ext.MessageHandler(telegram.ext.filters.ChatType.PRIVATE, handler))
        
        # 仅在配置有效时执行心跳逻辑
        if HB_FILE and HB_INTERVAL:
            # 1. 立即生成心跳文件（首次启动不延迟），防止看门狗误判
            logger.info("❤️ 正在创建初始心跳文件...")
            try:
                with open(HB_FILE, 'w') as f:
                    f.write(str(time.time()))
            except Exception as e:
                logger.error(f"❌ 首次写入心跳文件失败，请检查文件权限: {e}")
            
            # 2. 启动周期性心跳任务 
            app.job_queue.run_repeating(
                heartbeat_task, # 直接传递 async 函数
                interval=HB_INTERVAL
            )
        else:
            logger.warning("⚠️ 心跳功能已禁用 (缺少配置)。")
        
        logger.info(f"✅ 机器人已启动，正在监听...")
        
        # 启动轮询
        app.run_polling(allowed_updates=telegram.Update.ALL_TYPES, close_loop=False)

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