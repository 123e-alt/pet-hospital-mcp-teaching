import configparser
from openai import OpenAI

# 1. 读取 config.ini 配置信息
config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')

api_key = config.get('LLM', 'api_key')
base_url = config.get('LLM', 'base_url')
model_name = config.get('LLM', 'model_name')

# 2. 初始化 OpenAI 客户端
client = OpenAI(api_key=api_key, base_url=base_url)

# 初始化历史聊天记录列表 (用于实现记忆)
messages = []

print("=== 已开启无限对话模式，按 Ctrl+C 强行退出 ===")

# 3. 无限循环
while True:
    try:
        user_input = input("你: ")

        # 将用户输入加入历史记录
        messages.append({"role": "user", "content": user_input})

        # 4. 发送请求给LLM
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,  # 将所有的历史记录一并发送
            stream=True
        )

        # 5. 流式输出并收集完整的 AI 回复
        print("AI: ", end="")
        ai_reply = ""  # 用于拼接完整的 AI 回复
        for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                print(content, end="", flush=True)
                ai_reply += content  # 将每个片段拼接到完整的回复中

        print()  # 输出换行

        # 将 AI 完整的回复也加入历史记录，保持上下文连贯
        messages.append({"role": "assistant", "content": ai_reply})

    except KeyboardInterrupt:
        # 捕获用户按下 Ctrl+C 的操作，优雅退出
        print("\n已退出对话，再见！")
        break
