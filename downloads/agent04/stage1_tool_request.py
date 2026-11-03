import json
import sys
import urllib.error
import urllib.request


def main():
    if len(sys.argv) != 2:
        raise SystemExit("用法：python stage1_tool_request.py <ollama list 中的模型名>")

    tool = {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "在学习目录内创建文本文件，参数必须包含相对路径和完整正文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径，例如 学习笔记.txt"},
                    "content": {"type": "string", "description": "要写入的完整正文"}
                },
                "required": ["path", "content"],
                "additionalProperties": False
            }
        }
    }
    payload = {
        "model": sys.argv[1],
        "stream": False,
        "messages": [{
            "role": "user",
            "content": "请调用 write_file 创建 学习笔记.txt，正文必须为：今天学习 Function Calling"
        }],
        "tools": [tool]
    }
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Ollama HTTP {exc.code}：{detail}")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SystemExit(f"无法完成请求，请检查服务、端口或模型加载时间：{exc}")

    message = data.get("message", {})
    print("模型返回的消息：")
    print(json.dumps(message, ensure_ascii=False, indent=2))
    calls = message.get("tool_calls") or []
    if len(calls) != 1:
        raise SystemExit("本次验收未通过：预期恰好一次工具调用。")
    function = calls[0].get("function", {})
    arguments = function.get("arguments")
    expected = {
        "path": "学习笔记.txt",
        "content": "今天学习 Function Calling"
    }
    if function.get("name") != "write_file" or arguments != expected:
        raise SystemExit("本次验收未通过：工具名或参数与任务要求不一致。")
    print("阶段一通过：拿到预期工具名和参数。未执行工具，也未创建笔记文件。")


if __name__ == "__main__":
    main()
