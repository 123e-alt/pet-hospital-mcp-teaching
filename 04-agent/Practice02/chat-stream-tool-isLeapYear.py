import configparser
import json
import subprocess

from openai import OpenAI

# 1. 读取 config.ini 配置信息
config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')

api_key = config.get('LLM', 'api_key')
base_url = config.get('LLM', 'base_url')
model_name = config.get('LLM', 'model_name')

# 2. 初始化 OpenAI 客户端
client = OpenAI(api_key=api_key, base_url=base_url)


# ==================== function call 工具 ====================

def run_command(command):
    """执行本地命令并返回输出文本（自动兼容 UTF-8 / GBK 编码）"""
    raw = subprocess.run(command, shell=True, capture_output=True).stdout
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore").strip()


def get_date():
    """获取当前电脑的日期和时间。

    注意：这里不写任何 Python 计算时间的代码，
    而是直接调用本地 date / time 命令，取回命令输出。
    """
    date_text = run_command("date /t")
    time_text = run_command("time /t")
    return f"当前日期：{date_text}，当前时间：{time_text}"


def is_leap_year(year):
    """判断输入的年份是否为闰年。

    闰年规则（用 Python 代码直接计算，不依赖模型回答）：
    能被 4 整除且不能被 100 整除，或者能被 400 整除。
    """
    year = int(year)
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        return f"{year} 年是闰年。"
    return f"{year} 年不是闰年（平年）。"


# 工具名 -> 具体实现 的映射
TOOL_FUNCTIONS = {
    "getDate": get_date,
    "isLeapYear": is_leap_year,
}

# 提供给 LLM 的工具描述（function call schema）
tools = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": "获取当前电脑的日期和时间。当用户询问今天几号、现在几点、当前日期或时间时调用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "isLeapYear",
            "description": "判断某一年是否为闰年。当用户询问某一年是不是闰年时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "要判断的年份，例如 2024。",
                    }
                },
                "required": ["year"],
            },
        },
    },
]


def run_tool(name, arguments):
    """执行工具，并把结果转成字符串返回给 LLM"""
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return f"未知的工具：{name}"
    kwargs = json.loads(arguments) if arguments else {}
    return str(func(**kwargs))


# 初始化历史聊天记录列表 (用于实现记忆)
messages = [{"role": "system", "content": "你是一个乐于助人的AI助手，可以调用工具来获取准确信息，得到确切的计算结果。"}]

print("=== 已开启带工具调用的无限对话模式，按 Ctrl+C 强行退出 ===")

while True:
    try:
        user_input = input("你: ")
        messages.append({"role": "user", "content": user_input})

        # 4. 循环：直到 AI 不再请求工具为止
        while True:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=tools,
                stream=True,
            )

            ai_reply = ""
            tool_calls = {}  # index -> {"id":..., "name":..., "arguments":...}
            print("AI: ", end="")
            for chunk in response:
                delta = chunk.choices[0].delta
                # 普通文本：直接打印（打字机效果）
                if delta.content:
                    print(delta.content, end="", flush=True)
                    ai_reply += delta.content
                # 工具调用：流式分片，需要按 index 拼接
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        item = tool_calls.setdefault(
                            tc.index, {"id": "", "name": "", "arguments": ""}
                        )
                        if tc.id:
                            item["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                item["name"] += tc.function.name
                            if tc.function.arguments:
                                item["arguments"] += tc.function.arguments

            if tool_calls:
                # assistant 发起了工具调用：把这一步写入历史
                messages.append({
                    "role": "assistant",
                    "content": ai_reply or None,
                    "tool_calls": [
                        {
                            "id": item["id"],
                            "type": "function",
                            "function": {"name": item["name"], "arguments": item["arguments"]},
                        }
                        for _, item in sorted(tool_calls.items())
                    ],
                })

                # 逐个执行工具，并把结果作为 tool 消息回填
                for _, item in sorted(tool_calls.items()):
                    print()  # 换行，避免和打字机内容挤在一起
                    print(f"[调用工具] {item['name']}({item['arguments']})")
                    result = run_tool(item["name"], item["arguments"])
                    print(f"[工具返回] {result}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": item["id"],
                        "content": result,
                    })
                # 继续下一轮，让 AI 基于工具结果生成最终回答
                continue

            # 没有工具调用：普通回复结束
            print()
            messages.append({"role": "assistant", "content": ai_reply})
            break

    except KeyboardInterrupt:
        print("\n已退出对话，再见！")
        break
