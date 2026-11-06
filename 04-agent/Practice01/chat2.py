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

# 3. 获取用户输入
user_input = input("你: ")

# 4. 发送请求给LLM（第二阶段：Stream流式输出模式）
response = client.chat.completions.create(
    model=model_name,
    messages=[
        {"role": "user", "content": user_input}
    ],
    stream=True  # 修改点1：开启流式输出
)

# 5. 循环读取流式数据并实现打字机效果
print("AI: ", end="")  # 先打印AI前缀，不换行
for chunk in response: # 修改点2：遍历流式响应
    # 获取每次返回的增量内容
    content = chunk.choices[0].delta.content
    if content: # 确保内容不为空
        # 修改点3：end="" 表示不换行，flush=True 表示强制立刻刷新输出缓冲区
        print(content, end="", flush=True)

print() # 最后输出一个换行符，结束本次对话