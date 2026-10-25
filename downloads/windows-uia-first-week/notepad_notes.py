"""第三课：启动记事本 → 输入中文 → 通过另存为保存 → 读取文件验收。

请在 Windows 交互式桌面运行。运行期间让脚本完成输入，避免切换焦点。
仅操作本次启动后出现的新窗口；不能确认目标时停止，不接管旧窗口。
"""

import subprocess
import ctypes
import sys
import time
from datetime import datetime
from pathlib import Path

# 使用当前脚本的位置计算路径，与终端当前在哪个文件夹无关。
ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT.parent / "output"
TEXT = "第三课：完成记事本自动化流程\n\n一、UIA 基本原理\nUIA 将界面表示为控件树，程序通过属性定位控件，通过控件模式执行操作。\n\n二、识别窗口和控件\nDesktop 连接桌面；窗口句柄帮助区分窗口；记事本编辑区的类型是 Document。\n\n三、本次练习\n自动启动记事本，定位新的空白编辑区，输入学习笔记，通过另存为保存文件。\n\n四、结果验收\n检查目标文件存在，并核对磁盘正文是否与预期一致。\n\n五、我的思考\n文件存在不代表任务完全成功，还需要确认正文正确。\n"


def owned_by(handle, parent_handle):
    """沿 Win32 owner 链确认归属；跨进程时也不误操作别人的保存窗口。"""
    from ctypes import wintypes
    get_window = ctypes.windll.user32.GetWindow
    get_window.argtypes = (wintypes.HWND, wintypes.UINT)
    get_window.restype = wintypes.HWND  # 64 位句柄不能用默认的 32 位 int 接收。
    seen = set()
    while handle and handle not in seen:
        if handle == parent_handle:
            return True
        seen.add(handle)
        handle = get_window(handle, 4)  # GW_OWNER = 4，查询所属窗口。
    return False


def select_save_dialog(top_windows, child_windows, parent_handle, parent_pid):
    """合并两处 UIA 查询结果：有些模态对话框挂在记事本下面。

    子树中的窗口已有 UIA 父子关系证明；桌面窗口则必须同进程或 owner 链匹配。
    最后检查文件名框和保存按钮，避免将普通提示框当作另存为。
    """
    matches = {}
    for is_child, items in ((False, top_windows), (True, child_windows)):
        for item in items:
            info = item.element_info
            if item.handle == parent_handle or not item.is_visible():
                continue
            related = is_child or info.process_id == parent_pid or owned_by(item.handle, parent_handle)
            if not related:
                continue
            if info.class_name != "#32770" and not any(
                name in info.name.lower() for name in ("另存为", "save as")
            ):
                continue
            # descendants 的筛选参数不同于 child_window；这里枚举后读属性，
            # 不把 child_window 使用的 auto_id 参数传进 UIA build_condition。
            fields = [control for control in item.descendants(control_type="Edit")
                      if control.element_info.automation_id == "1001"]
            buttons = [control for control in item.descendants(control_type="Button")
                       if control.element_info.automation_id == "1"]
            if fields and buttons:
                matches[item.handle] = item
    if len(matches) > 1:
        raise RuntimeError("发现多个属于目标的保存对话框，停止以避免误操作")
    return next(iter(matches.values()), None)


def wait_for(description, probe, timeout=15):
    """轮询实际条件，而不是假设等待固定几秒后界面一定就绪。

    probe 成功时返回对象，暂时未就绪时返回 None。
    不吞掉编程错误：只有明确预期的“暂未出现”才应返回 None。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = probe()
        if result is not None:
            return result
        time.sleep(0.3)
    raise TimeoutError(f"等待超时：{description}")


def fill_filename(control, path):
    """用真实键盘输入更新文件名，再失焦提交；避免只更新了 UIA 显示值。

    一些文件对话框会在编辑结束时同步内部文件名，所以不能仅调用 SetValue。
    路径里的 +、括号等字符须转义，否则 type_keys 会将其解释成按键语法。
    """
    expected = str(path)
    escaped = "".join("{" + char + "}" if char in "+^%~(){}" else char
                      for char in expected)
    control.set_focus()
    control.type_keys("^a{BACKSPACE}", set_foreground=False)
    control.type_keys(escaped, with_spaces=True, pause=0.01, set_foreground=False)
    control.type_keys("{TAB}", set_foreground=False)

    def correct_value():
        actual = control.get_value()
        return actual if actual == expected else None

    try:
        actual = wait_for("文件名输入框内容与目标完整路径一致", correct_value, timeout=5)
    except TimeoutError:
        raise RuntimeError(f"文件名填写未通过核对。预期={expected!r}，"
                           f"实际={control.get_value()!r}；未点击保存") from None
    print(f"文件名框核对通过：{actual}")


def wait_for_saved_file(verify_file, query_dialog, timeout=15):
    """磁盘正文是成功依据；窗口查询只是辅助诊断。

    每次重新枚举窗口，不继续使用可能已销毁的对话框包装对象。
    仅容忍窗口查询的 COMError；文件读取和编程错误仍正常抛出。
    """
    from comtypes import COMError
    reported = False

    def probe():
        nonlocal reported
        result = verify_file()
        if result is not None:
            return result
        try:
            query_dialog()
        except COMError as exc:
            if not reported:
                print(f"[提示] 保存窗口查询暂不可用，继续核对磁盘文件：{exc}")
                reported = True
        return None

    return wait_for("保存文件且正文与预期完全一致", probe, timeout=timeout)


def main():
    if sys.platform != "win32":
        raise RuntimeError("需要 Windows 桌面环境")
    from pywinauto import Desktop

    desktop = Desktop(backend="uia")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    # 微秒时间戳生成独立文件，避免覆盖以前的学习成果。
    path = OUTPUT / f"lesson03_{datetime.now():%Y%m%d_%H%M%S_%f}.txt"
    if path.exists():
        raise FileExistsError(path)

    def notepad_windows():
        # 你的第一课输出已经确认，目标顶层窗口的 ClassName 是 Notepad。
        return desktop.windows(class_name="Notepad", visible_only=True)

    old_handles = {w.handle for w in notepad_windows()}
    print("[1/5] 启动记事本……")
    subprocess.Popen(["notepad.exe"])

    def find_new_window():
        new = [w for w in notepad_windows() if w.handle not in old_handles]
        if len(new) > 1:
            raise RuntimeError("出现多个新记事本窗口，无法唯一定位，请重试")
        return new[0] if new else None

    window = wait_for("新的记事本窗口；若应用复用了旧窗口，请先自行保存并关闭旧窗口后重试", find_new_window)
    print(f"目标：{window.window_text()!r}，句柄：{window.handle:#x}")

    def find_editor():
        # 新记事本是 Document，旧版本可能是 Edit。优先采用实际观察到的类型。
        for control_type in ("Document", "Edit"):
            items = window.descendants(control_type=control_type)
            items = [item for item in items if item.is_visible() and item.is_enabled()]
            if len(items) > 1:
                raise RuntimeError(f"找到多个 {control_type} 编辑区，请先检查控件树")
            if items:
                return items[0]
        return None

    print("[2/5] 定位编辑区并输入文字……")
    editor = wait_for("文本编辑区", find_editor)
    # type_keys 把文字作为键盘输入送入控件；它需要正确的键盘焦点。
    # 本课的固定 TEXT 没有 pywinauto 的快捷键保留符号。
    # 自定义内容若含 + ^ % ~ ( ) { }，需要先处理转义，不能直接照搬。
    # 不使用 Ctrl+A，避免覆盖记事本可能恢复出来的既有内容。
    existing = editor.iface_text.DocumentRange.GetText(-1)
    if existing.strip():
        raise RuntimeError("新窗口编辑区已有文字，为避免修改既有内容，停止操作")
    editor.set_focus()
    editor.type_keys(TEXT, with_spaces=True, with_newlines=True, pause=0.03)

    print("[3/5] 打开另存为……")
    # ^ 代表 Ctrl，+ 代表 Shift；Ctrl+Shift+S 是另存为快捷键。
    # 先明确恢复目标焦点，再发送快捷键；不要依赖此前输入留下的焦点。
    window.set_focus()
    window.type_keys("^+s", set_foreground=True)

    def find_save_dialog():
        return select_save_dialog(
            desktop.windows(visible_only=True),
            window.descendants(control_type="Window"),
            window.handle,
            window.element_info.process_id,
        )

    try:
        dialog = wait_for("另存为对话框", find_save_dialog, timeout=20)
    except TimeoutError:
        # 不重复发快捷键：对话框可能已经打开，重复按键反而会扰乱现场。
        # 保存真实 UIA 信息，下一次排查不用再猜标题或 AutomationId。
        log = OUTPUT / f"save_dialog_debug_{datetime.now():%Y%m%d_%H%M%S_%f}.txt"
        from contextlib import redirect_stdout
        with log.open("w", encoding="utf-8") as stream, redirect_stdout(stream):
            for item in desktop.windows(visible_only=True):
                try:
                    info = item.element_info
                    print(f"handle={item.handle:#x} PID={info.process_id} "
                          f"Name={info.name!r} ClassName={info.class_name!r}")
                    if info.class_name == "#32770":
                        desktop.window(handle=item.handle).print_control_identifiers(depth=4)
                except Exception as diagnostic_error:
                    print(f"[诊断读取失败] {diagnostic_error}")
            try:
                desktop.window(handle=window.handle).print_control_identifiers(depth=5)
            except Exception as diagnostic_error:
                print(f"[目标控件树读取失败] {diagnostic_error}")
        raise TimeoutError(f"未识别到目标另存为窗口。诊断已保存：{log}") from None
    print(f"已定位保存窗口：{dialog.window_text()!r}，句柄：{dialog.handle:#x}，"
          f"PID={dialog.element_info.process_id}")
    # 把真实窗口包装成查询对象，才能通过 child_window 指定属性定位。
    spec = desktop.window(handle=dialog.handle)
    filename = spec.child_window(auto_id="1001", control_type="Edit")
    filename.wait("visible enabled", timeout=10)
    fill_filename(filename.wrapper_object(), path)

    print(f"[4/5] 保存到：{path}")
    save = spec.child_window(auto_id="1", control_type="Button")
    save.wait("visible enabled", timeout=10)
    dialog_handle = dialog.handle  # 在点击前记录，关闭后不再向旧控件读取句柄。
    save.wrapper_object().invoke()

    # 保存后原对话框可能已经销毁，不再调用 spec.wait_not。
    # 用已记录的整数句柄做重新查询；窗口状态不取代文件内容验收。
    dialog_status = "尚未查询"

    def query_dialog():
        nonlocal dialog_status
        dialog_status = "无法确认（查询中或 UIA 错误）"
        present = any(item.handle == dialog_handle
                      for item in desktop.windows(visible_only=True))
        if not present:
            present = any(item.handle == dialog_handle
                          for item in window.descendants(control_type="Window")
                          if item.is_visible())
        dialog_status = "仍可见" if present else "未找到可见的原保存窗口"
        return present

    print("[5/5] 检查磁盘上的实际内容……")
    def verify_file():
        if not path.exists():
            return None
        try:
            raw = path.read_bytes()
        except PermissionError:
            return None  # 保存过程中可能短暂被占用。
        # 本机新记事本默认 UTF-8；同时兼容带 BOM 和常见旧编码。
        for encoding in ("utf-8-sig", "utf-16", "gb18030"):
            try:
                content = raw.decode(encoding)
            except UnicodeError:
                continue
            if content.replace("\r\n", "\n") == TEXT:
                return encoding
        return None

    try:
        encoding = wait_for_saved_file(verify_file, query_dialog)
    except TimeoutError:
        if not path.exists():
            raise RuntimeError(f"预期文件不存在：{path}；保存窗口状态：{dialog_status}。"
                               "请检查是否有覆盖确认或路径错误提示，不要确认覆盖既有文件。") from None
        raise RuntimeError(f"文件存在，但编码或正文核对未通过：{path}；"
                           f"文件大小={path.stat().st_size} 字节，预期正文={TEXT!r}") from None
    print(f"成功！正文核对通过，读取编码：{encoding}\n文件：{path}")
    # 保留窗口，让学习者检查结果；失败时也不自动关闭，方便排查现场。


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n操作已中断，请检查记事本当前状态。")
        sys.exit(130)
    except Exception as exc:
        print(f"[失败] {type(exc).__name__}: {exc}")
        print("保留窗口供检查。请记录失败步骤和提示；不要连续重复运行。")
        sys.exit(1)

