import sys

if getattr(sys, "frozen", False):
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32")
        user32 = ctypes.WinDLL("user32")

        hWnd = kernel32.GetConsoleWindow()
        if hWnd:
            GWL_EXSTYLE      = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW  = 0x00040000

            user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.GetWindowLongW.restype  = ctypes.c_long
            user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
            user32.SetWindowLongW.restype  = ctypes.c_long

            style = user32.GetWindowLongW(hWnd, GWL_EXSTYLE)
            style |= WS_EX_TOOLWINDOW
            style &= ~WS_EX_APPWINDOW
            user32.SetWindowLongW(hWnd, GWL_EXSTYLE, style)

            user32.ShowWindow(hWnd, 0)  # SW_HIDE

    except Exception:
        pass
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

    w, h = 420, 200
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    popup.geometry(f"{w}x{h}+{x}+{y}")

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

    default_font = tkfont.nametofont("TkDefaultFont")
    default_font.configure(size=13)
    root.option_add("*Font", default_font)
    root.title(APP_TITLE)
    root.geometry("1280x900")
    root.configure(bg="#111315")

    ctrl = Controller(app_name=APP_TITLE, author=AUTHOR)

    web_port = ctrl.config.get("web_port", 9999)
    ctrl.web_server_ok = False  

    try:
        t = start_web_server(ctrl, port=web_port)
        if t is not None:
            ctrl.web_server_ok = True
    except Exception as e:
        ctrl.log(f"WebUI start error: {e}")
        ctrl.web_server_ok = False

    if getattr(ctrl, "first_run", False):
        show_first_run_popup(root)

    if ctrl.config.get("always_on_top", False):
        root.attributes("-topmost", True)

    container = tk.Frame(root, bg="#111315")
    container.pack(fill="both", expand=True)

    pages = {}

    def show_page(name: str):
        for p in pages.values():
            p.pack_forget()
        pages[name].pack(fill="both", expand=True)

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

    pages["main"] = MainPage(container, ctrl, on_open_settings=open_settings)
    pages["main"].pack(fill="both", expand=True)

    def on_close():
        if messagebox.askokcancel("Exit", "Quit Total Scheduler?"):
            ctrl.shutdown()
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()



if __name__ == "__main__":
    main()
