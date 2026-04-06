# ---- 콘솔창 숨기기 (PyInstaller --console 빌드용, 작업표시줄에서도 숨김) ----
import sys

if getattr(sys, "frozen", False):
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32")
        user32 = ctypes.WinDLL("user32")

        # 콘솔 윈도우 핸들 얻기
        hWnd = kernel32.GetConsoleWindow()
        if hWnd:
            # 작업표시줄에서 안 보이도록 윈도우 스타일 변경
            GWL_EXSTYLE      = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW  = 0x00040000

            user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.GetWindowLongW.restype  = ctypes.c_long
            user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
            user32.SetWindowLongW.restype  = ctypes.c_long

            style = user32.GetWindowLongW(hWnd, GWL_EXSTYLE)
            # 작업표시줄용 플래그 제거, 툴윈도우 플래그 추가
            style |= WS_EX_TOOLWINDOW
            style &= ~WS_EX_APPWINDOW
            user32.SetWindowLongW(hWnd, GWL_EXSTYLE, style)

            # 그리고 창 자체도 숨김
            user32.ShowWindow(hWnd, 0)  # SW_HIDE

    except Exception:
        # 어떤 이유로 실패해도 앱은 계속 실행
        pass
# --------------------------------------------------------------------------
import tkinter as tk
from tkinter import messagebox
import tkinter.font as tkfont
from ui_main import MainPage
from ui_settings import SettingsPage
from controller import Controller
from web_server import start_web_server

APP_TITLE = "Total Scheduler"
AUTHOR = "CreDL - YOONS.B1"


def show_first_run_popup(root):
    popup = tk.Toplevel(root)
    popup.title("Copyright")
    popup.configure(bg="#111315")
    popup.transient(root)
    popup.grab_set()

    # 창 크기 및 위치(화면 중앙)
    w, h = 420, 200
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    popup.geometry(f"{w}x{h}+{x}+{y}")

    # 텍스트 라벨 (중앙 정렬)
    msg = (
        "Copyright © CreDL MEDIA Co., Ltd.\n\n"
        "Contact : antonio@credl.net\n"
        "See **Readme.txt** for instructions.\n"
        "This popup is shown only on first launch."
    )
    label = tk.Label(
        popup,
        text=msg,
        fg="white",
        bg="#111315",
        justify="center",
        font=("Segoe UI", 11),
    )
    label.pack(expand=True, fill="both", padx=20, pady=(20, 10))

    # OK 버튼
    ok_btn = tk.Button(
        popup,
        text="OK",
        width=10,
        bg="#3f88c5",
        fg="white",
        relief="flat",
        command=popup.destroy,
    )
    ok_btn.pack(pady=(0, 16))

    popup.focus_force()
    popup.wait_window()


def main():
    root = tk.Tk()

    # Surface Go 3용: 전체 기본 폰트 크기
    default_font = tkfont.nametofont("TkDefaultFont")
    default_font.configure(size=13)
    root.option_add("*Font", default_font)
    root.title(APP_TITLE)
    root.geometry("1280x900")
    root.configure(bg="#111315")

    # 컨트롤러는 딱 한 번만 생성
    ctrl = Controller(app_name=APP_TITLE, author=AUTHOR)

    # WebUI 서버 시작 (모바일/태블릿용)
    web_port = ctrl.config.get("web_port", 9999)
    ctrl.web_server_ok = False  # 기본은 False

    try:
        t = start_web_server(ctrl, port=web_port)
        if t is not None:
            ctrl.web_server_ok = True
    except Exception as e:
        ctrl.log(f"WebUI start error: {e}")
        ctrl.web_server_ok = False

    # --- 최초 실행시에만 저작권 팝업 표시 ---
    if getattr(ctrl, "first_run", False):
        show_first_run_popup(root)

    # 항상 위에 표시 옵션
    if ctrl.config.get("always_on_top", False):
        root.attributes("-topmost", True)

    # 메인 컨테이너
    container = tk.Frame(root, bg="#111315")
    container.pack(fill="both", expand=True)

    pages = {}

    def show_page(name: str):
        for p in pages.values():
            p.pack_forget()
        pages[name].pack(fill="both", expand=True)

    # 설정(셋업) 페이지 열기
    def open_settings():
        pages["settings"] = SettingsPage(
            container,
            ctrl,
            on_back=lambda: (
                pages["main"].enforce_shutter_from_config(),
                show_page("main"),
            ),
            root_ref=root,
            main_ref=pages["main"],
        )
        show_page("settings")

    # 메인 페이지 생성
    pages["main"] = MainPage(container, ctrl, on_open_settings=open_settings)
    pages["main"].pack(fill="both", expand=True)

    # 종료 처리
    def on_close():
        if messagebox.askokcancel("Exit", "Quit Total Scheduler?"):
            ctrl.shutdown()
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()



if __name__ == "__main__":
    main()
