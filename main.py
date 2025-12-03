import logging
import asyncio
import os
import json
from dotenv import load_dotenv
from telegram import Update, InputMediaPhoto, InputMediaVideo, InputMediaAudio, InputMediaDocument
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# -------------------------------
# 1. 初始化与日志
# -------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

# -------------------------------
# 2. 配置加载逻辑 (从 .env 获取文件路径，再加载 JSON)
# -------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
PROXY_URL = os.getenv("PROXY_URL")
CONFIG_PATH = os.getenv("CONFIG_PATH", "./config.json") # 默认值：config.json

DESTINATIONS = []
try:
    logger.info(f"📋 尝试从路径 {CONFIG_PATH} 加载业务配置...")
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
        DESTINATIONS = config_data.get('DESTINATIONS', [])
    logger.info("✅ 业务配置加载成功。")
except FileNotFoundError:
    logger.critical(f"⛔ 找不到配置文件: {CONFIG_PATH}，程序无法启动。")
    exit(1)
except json.JSONDecodeError as e:
    logger.critical(f"⛔ 配置文件 {CONFIG_PATH} 格式错误，请检查 JSON 语法: {e}")
    exit(1)

# 检查
if not BOT_TOKEN or not OWNER_ID:
    logger.critical("⛔ 未配置 BOT_TOKEN 或 OWNER_ID，程序无法启动。")
    exit(1)

# MediaGroup 缓存
MEDIA_GROUP_CACHE = {}


# -------------------------------
# 3. 核心转发逻辑 (保持不变)
# -------------------------------

async def forward_to_destinations(context: ContextTypes.DEFAULT_TYPE, message=None, media_list=None):
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
        
        topic_ids = dest.get('topic_ids') 
        topic_id = dest.get('topic_id')    

        target_threads = [None] 

        if topic_ids and isinstance(topic_ids, list):
            target_threads = topic_ids
        elif topic_id is not None:
            target_threads = [topic_id]

        # 对目标群组的每个话题（或主线程）执行发送
        for thread_id in target_threads:
            await send_action(chat_id, thread_id=thread_id)


# -------------------------------
# 4. 业务逻辑 (MediaGroup/Handler 保持不变)
# -------------------------------

async def process_media_group(context: ContextTypes.DEFAULT_TYPE, media_group_id: str):
    """处理相册缓存并发送"""
    await asyncio.sleep(2) 

    if media_group_id not in MEDIA_GROUP_CACHE:
        return
    
    messages = MEDIA_GROUP_CACHE.pop(media_group_id)
    messages.sort(key=lambda x: x.message_id)

    # 构建 InputMedia
    media_list = []
    for msg in messages:
        caption = msg.caption
        entities = msg.caption_entities
        
        if msg.photo:
            media_list.append(InputMediaPhoto(msg.photo[-1].file_id, caption=caption, caption_entities=entities))
        elif msg.video:
            media_list.append(InputMediaVideo(msg.video.file_id, caption=caption, caption_entities=entities))
        elif msg.audio:
            media_list.append(InputMediaAudio(msg.audio.file_id, caption=caption, caption_entities=entities))
        elif msg.document:
            media_list.append(InputMediaDocument(msg.document.file_id, caption=caption, caption_entities=entities))

    if media_list:
        logger.info(f"📤 正在转发相册 (共 {len(media_list)} 个文件)")
        await forward_to_destinations(context, media_list=media_list)


async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg or msg.chat.type != "private" or msg.from_user.id != OWNER_ID:
        return
    if msg.text and msg.text.startswith("/"):
        return

    # --- 场景 A: 相册消息 ---
    if msg.media_group_id:
        is_first = msg.media_group_id not in MEDIA_GROUP_CACHE
        
        if is_first:
            MEDIA_GROUP_CACHE[msg.media_group_id] = []
        
        MEDIA_GROUP_CACHE[msg.media_group_id].append(msg)

        if is_first:
            context.application.create_task(process_media_group(context, msg.media_group_id))
        return

    # --- 场景 B: 普通消息 ---
    logger.info(f"📤 正在转发单条消息 (ID: {msg.message_id})")
    await forward_to_destinations(context, message=msg)


# -----------------------------
# 主程序
# -----------------------------
def main():
    builder = ApplicationBuilder().token(BOT_TOKEN)
    
    if PROXY_URL and PROXY_URL.strip():
        builder.proxy(PROXY_URL)
        logger.info(f"🌐 代理已配置: {PROXY_URL}")

    app = builder.build()
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE, handler))

    logger.info(f"✅ 机器人已启动，正在监听 Owner ID: {OWNER_ID}")
    logger.info(f"📋 配置文件路径: {CONFIG_PATH}")
    logger.info(f"📋 总转发目标数量: {len(DESTINATIONS)} 个配置项")

    app.run_polling()

if __name__ == "__main__":
    main()