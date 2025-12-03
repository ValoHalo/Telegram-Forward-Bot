# TG 转发机器人
把你私发给机器人的消息转发到你的群组中，主要是方便我偷懒（）

# 要求
Python 3.12 （我没有测试过更多版本，已知3.14不支持）

# 用法
 1. 去 Botfarther 申请一个 Bot，并得到其 token
 2. 获取你自己的账号 ID，以及想要转发到的群组的 ID （一般是-100开头）和话题 ID（如果不是有话题的群组则不需要）
 3. 按照注释填写 `.env` 和 `config.targets.json` 文件中的内容
 4. 运行 `start.bot`，会自动生成虚拟环境，如果你不想生成可以直接运行 `main.py`，记得确保满足 `requirements.txt` 中的要求
 5. 把你的机器人拉到群组中，并设置为管理员（设置一次即可，之后撤销也可以正常工作）。否则会返回 `Chat not found` 错误

# TODO
 - [x]  配置文件独立于程序
 - [x]  正常转发 MediaGroup
 - [ ]  转发显示来源
 - [ ]  处理收到的信息中的链接（如把域名中的 twitter 改成 fxtwitter ）
 - [ ]  命令？ ~~（没想过能用什么命令）~~ 

# Special Thanks
- Gemini
- ChatGPT