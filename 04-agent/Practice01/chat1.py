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

# 3. 获取用户输入（单次对话）
user_input = input("你: ")

# 4. 发送请求给LLM（第一阶段：非Stream输出模式）
response = client.chat.completions.create(
    model=model_name,
    messages=[
        {"role": "user", "content": user_input}
    ],
    stream=False
)

# 5. 打印AI回复
print(f"AI: {response.choices[0].message.content}")