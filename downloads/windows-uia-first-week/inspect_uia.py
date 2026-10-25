"""第一课：通过 UI Automation 观察窗口和控件（不点击、不修改内容）。

运行：python lesson01_uia.py
先手动打开记事本。多个记事本窗口存在时，用 --handle 指定目标。
"""

import argparse
import sys


def describe(control):
    """读取 UIA 属性。Name 是可访问名称，不一定等于屏幕上的完整文字。"""
    info = control.element_info
    return (
        f"Name={info.name!r}, Type={info.control_type}, "
        f"AutomationId={info.automation_id!r}, ClassName={info.class_name!r}"
    )


def show_tree(control, depth, budget, level=0):
    """递归读取直接子控件，缩进表示父子关系。

    depth 限制层数，budget 限制总节点数，避免控件过多时输出失控。
    UIA 是实时查询：窗口关闭后，原来的控件对象可能立即失效。
    因此每个节点都单独捕获异常，保留其他节点的观察结果。
    """
    if budget[0] <= 0:
        return
    budget[0] -= 1
    try:
        print("  " * level + describe(control))
        if level < depth:
            for child in control.children():
                if budget[0] <= 0:
                    break
                show_tree(child, depth, budget, level + 1)
    except Exception as exc:
        print("  " * level + f"[读取失败] {type(exc).__name__}: {exc}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    # int(value, 0) 同时支持十进制和 0x 开头的十六进制句柄。
    parser.add_argument("--handle", type=lambda value: int(value, 0))
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--max-nodes", type=int, default=100)
    args = parser.parse_args()
    if args.depth < 0 or args.max_nodes < 1:
        parser.error("depth 必须非负，max-nodes 必须大于 0")
    if sys.platform != "win32":
        print("本练习只能在 Windows 上运行。")
        return 1
    try:
        from pywinauto import Desktop
    except ImportError:
        print("缺少依赖，请执行：python -m pip install -r requirements.txt")
        return 1

    # Desktop 是自动化客户端入口；uia 表示使用微软 UI Automation 后端。
    # 软件通过 Provider 暴露控件；Python 通过 UIA 读取它们的属性和层级。
    desktop = Desktop(backend="uia")
    windows = desktop.windows(visible_only=True)
    candidates = []
    print("=== 可见顶层窗口：句柄、进程 ID、标题 ===")
    for window in windows:
        try:
            info = window.element_info
            print(f"{window.handle:#x} | PID={info.process_id} | {info.name!r}")
            # 这是方便入门的候选筛选，不是唯一身份验证；其他软件标题也可能包含记事本。
            if "notepad" in info.class_name.lower() or any(
                word in info.name.lower() for word in ("记事本", "notepad")
            ):
                candidates.append(window)
        except Exception as exc:
            print(f"[窗口已变化或无法访问] {type(exc).__name__}: {exc}")

    if args.handle is not None:
        # 先构造查询条件，再等待窗口存在，最后取得实际控件包装对象。
        target_spec = desktop.window(handle=args.handle)
        target_spec.wait("exists visible", timeout=5)
        target = target_spec.wrapper_object()
    elif len(candidates) == 1:
        target = candidates[0]
    else:
        print("\n请打开记事本；若存在多个候选，请根据上表用 --handle 0x句柄 指定窗口。")
        return 1

    print("\n=== 目标窗口的控件树 ===")
    budget = [args.max_nodes]  # 可变列表让递归调用共享剩余节点数。
    show_tree(target, args.depth, budget)
    if budget[0] == 0:
        print("[已到节点上限，可用 --max-nodes 调整]")
    # 本课只观察属性。后续课程再学习 Invoke、Value、Text 等控件模式。
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户中断。")
        sys.exit(130)
    except Exception as exc:
        print(f"[执行失败] {type(exc).__name__}: {exc}")
        print("请检查窗口是否仍打开，以及目标程序与 Python 的权限是否一致。")
        sys.exit(1)
