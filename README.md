# TG 转发机器人
把你私发给机器人的消息转发到你的群组中，主要是方便我偷懒（）

# 要求
Python 3.12 （使用的是 20.7 版本的 Telegram bot Python 库，已知 Python 3.14 不支持）

# 用法
 1. 去 Botfarther 申请一个 Bot，并得到其 token
 2. 获取你自己的账号 ID，以及想要转发到的群组的 ID （一般是-100开头）和话题 ID（如果不是有话题的群组则不需要）
 3. 填写 `config.json` 文件中的内容。由于 json 中不能添加注释，请参考下面的注释进行修改
```json
{
  "bot": { // 基础配置
    "token": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", // 在 Botfather 处申请到的机器人 token
    "owner_id": 123456789, // 你的 Telegram ID
    "proxy_url": "socks5://0.0.0.0:12345" // 代理地址，不需要则留空：""
  },
  "watchdog": { // watchdog 机制的配置，一般无需修改
    "heartbeat_file": "bot.heartbeat", // 心跳文件的名字
    "heartbeat_interval_s": 60, // 生成心跳文件的时间间隔
    "heartbeat_timeout_s": 300, // 心跳文件超时的时间
    "restart_delay_s": 5, // 超时或错误后，重启 main.py 前的延时
    "max_consecutive_restarts": 5 // 最大连续重启次数
  },
  "destinations": [
    {
      "chat_id": -1001234567890, // 群组 ID
      "topic_ids": [] // 话题 ID，留空表示群组没有开启话题功能
    },
    {
      "chat_id": -1005555555555,
      "topic_ids": [1]
    },
    {
      "chat_id": -1004444444444,
      "topic_ids": [1, 2, 3]
    }
  ]
}
```
 1. 运行 `start.bot`，会自动生成虚拟环境 `.venv`，记得确保满足 `requirements.txt` 中的要求
 2. 把你的机器人拉到群组中，并设置为管理员（设置一次即可，之后撤销也可以正常工作）。否则会返回 `Chat not found` 错误（应该是 Telegram 官方的反 spam 限制）。

# TODO
 - [x]  配置文件独立于程序
 - [x]  正常转发 MediaGroup
 - [x]  添加 Watchdog 机制
 - [ ]  转发显示来源
 - [ ]  处理收到的信息中的链接（如把域名中的 twitter 改成 fxtwitter）
 - [ ]  命令？ ~~（没想过能用什么命令）~~ 

# Special Thanks
- Gemini
- ChatGPT