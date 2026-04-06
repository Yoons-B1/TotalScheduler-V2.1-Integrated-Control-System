import tkinter as tk
from tkinter import ttk, messagebox
import socket

BG = "#111315"
PANEL = "#171a1d"
ACCENT = "#2a9d8f"
ACCENT2 = "#3f88c5"  # Save 버튼용 살짝 다른 색
TEXT = "#e8e8e8"
SUB = "#a9b2ba"


class SettingsPage(tk.Frame):
    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _update_webserver_info(self):
        # IP 텍스트
        ip = self._get_local_ip()
        port = self.ctrl.config.get("web_port", 9999)

        self.ws_label.config(text=f"WebServer - {ip} : {port}")

        # 상태 점 (web_server_ok 플래그 기반)
        ok = getattr(self.ctrl, "web_server_ok", False)
        self.ws_canvas.delete("all")
        color = "#6dc36d" if ok else "#e45858"
        self.ws_canvas.create_oval(2, 2, 12, 12, fill=color, outline=color)

    def _on_web_restart(self):
        # 포트 입력값 검증 + 저장
        s = self.ws_port_var.get().strip()
        if not s:
            s = "9999"
        try:
            port = int(s)
        except ValueError:
            messagebox.showerror("WebServer", "Port must be a number.")
            return

        # 설정에 저장
        self.ctrl.config["web_port"] = port
        # 컨트롤러에 save 메서드가 있다면 호출
        if hasattr(self.ctrl, "save_config"):
            self.ctrl.save_config()

        # 라벨 업데이트
        self._update_webserver_info()

        # *** 중요한 부분 ***
        # 여기서는 실제로 서버를 재시작하지 않고,
        # "앱을 한번 완전히 종료 후 다시 실행해 주세요" 라고 안내하는 걸 추천.
        messagebox.showinfo(
            "WebServer",
            "Port is saved.\n\nPlease close and restart TotalScheduler to apply the new port."
        )

    def __init__(self, master, ctrl, on_back, root_ref=None, main_ref=None):
        super().__init__(master, bg=BG)
        self.ctrl = ctrl
        self.on_back = on_back
        self.root_ref = root_ref
        self.main_ref = main_ref

        self._pc_edit_index = None
        self._beam_edit_index = None
        self._tcp_edit_index = None
        self._pc_dots = {}
        self._beam_widgets = {}
        self._log_buffer = []

        # OSC GUI용 내부 저장소
        self.osc_enable_vars = []
        self.osc_label_entries = []
        self.osc_ip_entries = []
        self.osc_port_entries = []
        self.osc_addr_entries = []
        self.osc_value_entries = []
        self.osc_type_boxes = []

        # 슬라이더 GUI용 내부 저장소
        self.slider_enable_vars = []
        self.slider_label_entries = []
        self.slider_ip_entries = []
        self.slider_port_entries = []
        self.slider_addr_entries = []
        self.slider_min_entries = []
        self.slider_max_entries = []
        self.slider_type_boxes = []

        # --------------- 상단 타이틀 ---------------
        title = tk.Label(
            self,
            text="Setup",
            fg=TEXT,
            bg=BG,
            font=("Segoe UI", 24, "bold"),   # 메인페이지 Total Scheduler와 비슷한 크기
        )
        title.pack(pady=(20, 8))             # 중앙 정렬 (anchor 없음)

        # --------------- 헤더 영역 (버튼들) ---------------
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", pady=(0, 8))

        # 오른쪽: Save Settings + Back
        tk.Button(
            header,
            text="Save Settings",
            bg=ACCENT2,
            fg="white",
            relief="flat",
            width=12,
            height=2,
            command=self.save,
        ).pack(side="right", padx=(8, 16))

        tk.Button(
            header,
            text="Back",
            bg=ACCENT,
            fg="white",
            relief="flat",
            width=10,
            height=2,
            command=on_back,
        ).pack(side="right", padx=(0, 8))


        # --------------- 바디 레이아웃 ---------------
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=10)

        # 왼쪽: 스크롤 가능한 설정 폼
        left_wrap = tk.Frame(body, bg=BG)
        left_wrap.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.canvas = tk.Canvas(left_wrap, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        vs = ttk.Scrollbar(left_wrap, orient="vertical", command=self.canvas.yview)
        vs.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=vs.set)

        self.inner = tk.Frame(self.canvas, bg=BG)
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        # 오른쪽: 옵션 + 로그뷰
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="y")

        opts = tk.Frame(right, bg=BG)
        opts.pack(anchor="nw", padx=8, pady=8)

        self.var_top = tk.BooleanVar(value=self.ctrl.config.get("always_on_top", False))
        self.var_shut = tk.BooleanVar(
            value=self.ctrl.config.get("enable_shutter_shortcut", False)
        )
        self.var_showlog = tk.BooleanVar(
            value=self.ctrl.config.get("show_log_view", True)
        )

        tk.Checkbutton(
            opts,
            text="Always on top",
            variable=self.var_top,
            fg=TEXT,
            bg=BG,
            selectcolor=BG,
            activebackground=BG,
        ).pack(anchor="w")

        tk.Checkbutton(
            opts,
            text="Shutter & Shortcut",
            variable=self.var_shut,
            fg=TEXT,
            bg=BG,
            selectcolor=BG,
            activebackground=BG,
        ).pack(anchor="w", pady=(4, 4))

        tk.Checkbutton(
            opts,
            text="Show Log View",
            variable=self.var_showlog,
            fg=TEXT,
            bg=BG,
            selectcolor=BG,
            activebackground=BG,
            command=self._toggle_log_view,
        ).pack(anchor="w")

        # LOG VIEW
        self.log_label = tk.Label(right, text="Log View", fg=TEXT, bg=BG)
        self.log_view = tk.Text(
            right,
            height=24,
            width=36,
            bg="#0f1113",
            fg=SUB,
            insertbackground=SUB,
            highlightbackground="#0d0f12",
            highlightthickness=1,
            state="disabled",
        )

        # Log view is always visible; checkbox now controls live update (play/pause)
        self.log_label.pack(anchor="w", padx=8, pady=(8, 4))
        self.log_view.pack(
            anchor="nw", padx=8, pady=(0, 8), fill="y"
        )

        # --------------- PCs 폼 ---------------
        tk.Label(self.inner, text="PCs", fg=TEXT, bg=BG, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 6))

        row = tk.Frame(self.inner, bg=BG)
        row.pack(fill="x", pady=2)

        self.pc_name = tk.Entry(row)
        self.pc_name.pack(side="left", padx=3)
        self.pc_ip = tk.Entry(row, width=18)
        self.pc_ip.pack(side="left", padx=3)
        self.pc_mac = tk.Entry(row, width=20)
        self.pc_mac.pack(side="left", padx=3)
        self.pc_port = tk.Entry(row, width=6)
        self.pc_port.pack(side="left", padx=3)

        tk.Button(
            row,
            text="Save/ADD",
            width=8,
            bg=ACCENT,
            fg="white",
            relief="flat",
            command=self.add_pc,
        ).pack(side="left", padx=6)

        self._set_placeholder(self.pc_name, "PC name")
        self._set_placeholder(self.pc_ip, "PC IP")
        self._set_placeholder(self.pc_mac, "MAC Address")
        self.pc_port.insert(0, "5050")

        self.pc_container = tk.Frame(
            self.inner,
            bg=PANEL,
            highlightbackground="#0d0f12",
            highlightthickness=1,
        )
        self.pc_container.pack(fill="x", pady=(4, 12))

        # --------------- Projectors 폼 ---------------
        tk.Label(self.inner, text="Projectors", fg=TEXT, bg=BG, font=("Segoe UI", 11, "bold")).pack(
            anchor="w", pady=(0, 6)
        )

        brow = tk.Frame(self.inner, bg=BG)
        brow.pack(fill="x", pady=2)

        self.b_name = tk.Entry(brow)
        self.b_name.pack(side="left", padx=3)
        self.b_ip = tk.Entry(brow, width=18)
        self.b_ip.pack(side="left", padx=3)
        self.b_port = tk.Entry(brow, width=6)
        self.b_port.pack(side="left", padx=3)
        self.b_pass = tk.Entry(brow, width=24)
        self.b_pass.pack(side="left", padx=3)

        tk.Button(
            brow,
            text="Save/ADD",
            width=8,
            bg=ACCENT,
            fg="white",
            relief="flat",
            command=self.add_beam,
        ).pack(side="left", padx=6)

        self._set_placeholder(self.b_name, "BEAM name")
        self._set_placeholder(self.b_ip, "BEAM IP")
        self.b_port.insert(0, "4352")
        self._set_placeholder(self.b_pass, "PJLink password or blank")

        self.beam_container = tk.Frame(
            self.inner,
            bg=PANEL,
            highlightbackground="#0d0f12",
            highlightthickness=1,
        )
        self.beam_container.pack(fill="x", pady=(4, 12))

        # --------------- TCP Outputs 폼 ---------------
        tk.Label(self.inner, text="TCP Outputs", fg=TEXT, bg=BG, font=("Segoe UI", 11, "bold")).pack(
            anchor="w", pady=(0, 6)
        )

        trow = tk.Frame(self.inner, bg=BG)
        trow.pack(fill="x", pady=2)

        self.tcp_name = tk.Entry(trow)
        self.tcp_name.pack(side="left", padx=3)
        self.tcp_ip = tk.Entry(trow, width=18)
        self.tcp_ip.pack(side="left", padx=3)
        self.tcp_port = tk.Entry(trow, width=6)
        self.tcp_port.pack(side="left", padx=3)
        self.tcp_data = tk.Entry(trow, width=32)
        self.tcp_data.pack(side="left", padx=3)

        tk.Button(
            trow,
            text="Save/ADD",
            width=8,
            bg=ACCENT,
            fg=TEXT,
            relief="flat",
            command=self.add_tcp,
        ).pack(side="left", padx=6)

        self._set_placeholder(self.tcp_name, "TCP name")
        self._set_placeholder(self.tcp_ip, "TCP IP")
        self.tcp_port.insert(0, "80")
        self._set_placeholder(self.tcp_data, "Data (message to send)")

        self.tcp_container = tk.Frame(
            self.inner,
            bg=PANEL,
            highlightbackground="#0d0f12",
            highlightthickness=1,
        )
        self.tcp_container.pack(fill="x", pady=(4, 12))

        # --------------- OSC Buttons 폼 ---------------
        tk.Label(self.inner, text="OSC Buttons", fg=TEXT, bg=BG, font=("Segoe UI", 11, "bold")).pack(
            anchor="w", pady=(4, 6)
        )

        max_osc = 6
        osc_cfg = self.ctrl.config.setdefault("osc_buttons", [])
        while len(osc_cfg) < max_osc:
            osc_cfg.append(
                {
                    "enabled": False,
                    "label": "",
                    "ip": "",
                    "port": 7000,
                    "address": "",
                    "value": "",
                    "type": "float",
                }
            )

        for i in range(max_osc):
            cfg = osc_cfg[i]

            # 1줄: Enable + Label
            row1 = tk.Frame(self.inner, bg=BG)
            row1.pack(fill="x", pady=(2, 0))

            var_en = tk.BooleanVar(value=bool(cfg.get("enabled", False)))
            cb = tk.Checkbutton(
                row1,
                text=f"OSC {i+1}",
                variable=var_en,
                fg=TEXT,
                bg=BG,
                selectcolor=BG,
                activebackground=BG,
            )
            cb.pack(side="left", padx=(0, 4))

            e_label = tk.Entry(row1, width=28)
            e_label.insert(0, cfg.get("label", ""))
            e_label.pack(side="left", padx=3)

            tk.Label(row1, text="", bg=BG).pack(side="left", expand=True, fill="x")

            # 2줄: IP, Port, Address, Value, Type + Send
            row2 = tk.Frame(self.inner, bg=BG)
            row2.pack(fill="x", pady=(0, 4))

            e_ip = tk.Entry(row2, width=16)
            e_ip.insert(0, cfg.get("ip", ""))
            e_ip.pack(side="left", padx=3)

            e_port = tk.Entry(row2, width=6)
            e_port.insert(0, str(cfg.get("port", 7000)))
            e_port.pack(side="left", padx=3)

            e_addr = tk.Entry(row2, width=20)
            e_addr.insert(0, cfg.get("address", ""))
            e_addr.pack(side="left", padx=3)

            e_val = tk.Entry(row2, width=8)
            stored_val = str(cfg.get("value", "")).strip()
            if stored_val:
                e_val.insert(0, stored_val)
            else:
                e_val.insert(0, "value(1,0)")  # 안내 문구
            e_val.pack(side="left", padx=3)

            box = ttk.Combobox(
                row2,
                width=8,
                state="readonly",
                values=["float", "int", "string"],
            )
            box.set(str(cfg.get("type", "float")))
            box.pack(side="left", padx=3)

            tk.Button(
                row2,
                text="Send",
                width=6,
                bg="#3f88c5",
                fg="white",
                relief="flat",
                command=lambda idx=i: self._send_osc_row(idx),
            ).pack(side="left", padx=4)

            self.osc_enable_vars.append(var_en)
            self.osc_label_entries.append(e_label)
            self.osc_ip_entries.append(e_ip)
            self.osc_port_entries.append(e_port)
            self.osc_addr_entries.append(e_addr)
            self.osc_value_entries.append(e_val)
            self.osc_type_boxes.append(box)

        # --------------- OSC Sliders 폼 (2개) ---------------
        tk.Label(self.inner, text="OSC Sliders", fg=TEXT, bg=BG, font=("Segoe UI", 11, "bold")).pack(
            anchor="w", pady=(8, 6)
        )

        slider_cfg = self.ctrl.config.setdefault("osc_sliders", [])
        while len(slider_cfg) < 2:
            slider_cfg.append(
                {
                    "enabled": False,
                    "label": "",
                    "ip": "",
                    "port": 7000,
                    "address": "",
                    "min": 0,
                    "max": 100,
                    "type": "float",
                }
            )

        for i in range(2):
            cfg = slider_cfg[i]

            srow1 = tk.Frame(self.inner, bg=BG)
            srow1.pack(fill="x", pady=(2, 0))

            s_var_en = tk.BooleanVar(value=bool(cfg.get("enabled", False)))
            tk.Checkbutton(
                srow1,
                text=f"SLIDER {i+1}",
                variable=s_var_en,
                fg=TEXT,
                bg=BG,
                selectcolor=BG,
                activebackground=BG,
            ).pack(side="left", padx=(0, 4))

            s_label = tk.Entry(srow1, width=28)
            s_label.insert(0, cfg.get("label", ""))
            s_label.pack(side="left", padx=3)

            tk.Label(srow1, text="", bg=BG).pack(side="left", expand=True, fill="x")

            srow2 = tk.Frame(self.inner, bg=BG)
            srow2.pack(fill="x", pady=(0, 6))

            s_ip = tk.Entry(srow2, width=16)
            s_ip.insert(0, cfg.get("ip", ""))
            s_ip.pack(side="left", padx=3)

            s_port = tk.Entry(srow2, width=6)
            s_port.insert(0, str(cfg.get("port", 7000)))
            s_port.pack(side="left", padx=3)

            s_addr = tk.Entry(srow2, width=20)
            s_addr.insert(0, cfg.get("address", ""))
            s_addr.pack(side="left", padx=3)

            s_min = tk.Entry(srow2, width=6)
            s_min.insert(0, str(cfg.get("min", 0)))
            s_min.pack(side="left", padx=3)

            s_max = tk.Entry(srow2, width=6)
            s_max.insert(0, str(cfg.get("max", 100)))
            s_max.pack(side="left", padx=3)

            s_box = ttk.Combobox(
                srow2,
                width=8,
                state="readonly",
                values=["float", "int", "string"],
            )
            s_box.set(str(cfg.get("type", "float")))
            s_box.pack(side="left", padx=3)

            self.slider_enable_vars.append(s_var_en)
            self.slider_label_entries.append(s_label)
            self.slider_ip_entries.append(s_ip)
            self.slider_port_entries.append(s_port)
            self.slider_addr_entries.append(s_addr)
            self.slider_min_entries.append(s_min)
            self.slider_max_entries.append(s_max)
            self.slider_type_boxes.append(s_box)

        # --------------- Auto Schedule ---------------
        tk.Label(
            self.inner,
            text="Auto Schedule",
            fg=TEXT,
            bg=BG,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(8, 6))

        # 스케줄 설정 데이터 (config) 가져오기 + 기본값
        sch_cfg = self.ctrl.config.setdefault("schedule", {})
        raw_days = sch_cfg.get("enabled_days", [True, True, True, True, True, True, False])
        if len(raw_days) != 7:
            raw_days = (list(raw_days) + [True] * 7)[:7]

        # Enable 플래그 + 요일 변수들
        self.var_schedule_enabled = tk.BooleanVar(
            value=sch_cfg.get("enabled", True)
        )
        self.day_vars = [tk.BooleanVar(value=v) for v in raw_days]
        self.var_reboot_after_on = tk.BooleanVar(
            value=sch_cfg.get("reboot_after_on_enabled", False)
        )
        self.var_reboot_delay = tk.IntVar(
            value=int(sch_cfg.get("reboot_delay_min", 5) or 5)
        )

        # 프레임 생성
        sch = tk.Frame(self.inner, bg=BG)
        sch.pack(fill="x")

        # Enable Auto Schedule 체크박스
        tk.Checkbutton(
            sch,
            text="Enable Auto Schedule",
            variable=self.var_schedule_enabled,
            fg=TEXT,
            bg=BG,
            selectcolor=BG,
            activebackground=BG,
        ).grid(row=0, column=0, columnspan=7, sticky="w", padx=4, pady=(0, 4))

        # 요일 체크박스 (Mon~Sun)
        for col, (dvar, name) in enumerate(
            zip(self.day_vars, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        ):
            tk.Checkbutton(
                sch,
                text=name,
                variable=dvar,
                fg=TEXT,
                bg=BG,
                selectcolor=BG,
                activebackground=BG,
            ).grid(row=1, column=col, padx=4)

        # ALL ON 시간 설정
        t1 = tk.Frame(self.inner, bg=BG)
        t1.pack(fill="x", pady=(6, 2))
        tk.Label(t1, text="ALL ON", fg=TEXT, bg=BG).pack(side="left", padx=4)

        self.on_hour = ttk.Combobox(
            t1,
            width=4,
            state="readonly",
            values=[f"{h:02d}" for h in range(24)],
        )
        self.on_hour.pack(side="left", padx=2)
        tk.Label(t1, text=":", fg=TEXT, bg=BG).pack(side="left")
        self.on_min = ttk.Combobox(
            t1,
            width=4,
            state="readonly",
            values=[f"{m:02d}" for m in range(60)],   # 00~59
        )
        self.on_min.pack(side="left", padx=2)

        # ALL OFF 시간 설정
        t2 = tk.Frame(self.inner, bg=BG)
        t2.pack(fill="x", pady=(2, 8))
        tk.Label(t2, text="ALL OFF", fg=TEXT, bg=BG).pack(side="left", padx=4)
        self.off_hour = ttk.Combobox(
            t2,
            width=4,
            state="readonly",
            values=[f"{h:02d}" for h in range(24)],
        )
        self.off_hour.pack(side="left", padx=2)
        tk.Label(t2, text=":", fg=TEXT, bg=BG).pack(side="left")
        self.off_min = ttk.Combobox(
            t2,
            width=4,
            state="readonly",
            values=[f"{m:02d}" for m in range(60)],   # 00~59
        )
        self.off_min.pack(side="left", padx=2)

        # ALL ON 후 PC 자동 REBOOT 옵션
        reboot_frame = tk.Frame(self.inner, bg=BG)
        reboot_frame.pack(fill="x", pady=(2, 8))

        tk.Checkbutton(
            reboot_frame,
            text="Reboot PCs after ALL ON",
            variable=self.var_reboot_after_on,
            fg=TEXT,
            bg=BG,
            selectcolor=BG,
            activebackground=BG,
        ).pack(side="left", padx=4)

        tk.Label(
            reboot_frame,
            text="Delay (min):",
            fg=TEXT,
            bg=BG,
        ).pack(side="left", padx=(8, 2))

        self.reboot_delay_entry = tk.Spinbox(
            reboot_frame,
            from_=1,
            to=120,
            textvariable=self.var_reboot_delay,
            width=4,
        )
        self.reboot_delay_entry.pack(side="left", padx=2)

        # 초기 시간값 세팅 (config에서 가져오기)
        on_str = sch_cfg.get("all_on_time", "09:00")
        off_str = sch_cfg.get("all_off_time", "18:00")
        try:
            on_h, on_m = on_str.split(":")
            off_h, off_m = off_str.split(":")
        except Exception:
            on_h, on_m, off_h, off_m = "09", "00", "18", "00"

        self.on_hour.set(on_h)
        self.on_min.set(on_m)
        self.off_hour.set(off_h)
        self.off_min.set(off_m)

        # --- WebServer info (footer 바로 위) ---
        ws_frame = tk.Frame(self.inner, bg="#111315")
        ws_frame.pack(fill="x", pady=(10, 6))

        # 상태 점 (초록 / 빨강)
        self.ws_canvas = tk.Canvas(ws_frame, width=14, height=14,
                                   bg="#111315", highlightthickness=0)
        self.ws_canvas.pack(side="left", padx=(4, 6))

        # "WebServer - IP : Port" 텍스트
        self.ws_label = tk.Label(
            ws_frame,
            text="WebServer - ...",
            fg="#c7ced8",
            bg="#111315",
            font=("Segoe UI", 10)
        )
        self.ws_label.pack(side="left")

        # 포트 레이블
        port_label = tk.Label(
            ws_frame,
            text="Port",
            fg="#8b95a3",
            bg="#111315",
            font=("Segoe UI", 9)
        )
        port_label.pack(side="left", padx=(12, 4))

        # 포트 입력칸 (설정값 사용, 없으면 9999)
        self.ws_port_var = tk.StringVar()
        self.ws_port_var.set(str(self.ctrl.config.get("web_port", 9999)))
        self.ws_port_entry = tk.Entry(
            ws_frame,
            textvariable=self.ws_port_var,
            width=6,
            bg="#181c22",
            fg="#f5f5f5",
            insertbackground="#f5f5f5",
            relief="solid",
            borderwidth=1
        )
        self.ws_port_entry.pack(side="left")

        # Restart 버튼
        self.ws_restart_btn = tk.Button(
            ws_frame,
            text="Restart",
            command=self._on_web_restart,
            bg="#2f3844",
            fg="#e0e5ee",
            activebackground="#3b4654",
            activeforeground="#ffffff",
            bd=0,
            padx=8,
            pady=2,
            font=("Segoe UI", 9, "bold")
        )
        self.ws_restart_btn.pack(side="left", padx=(8, 0))

        # 처음 화면 표시 업데이트
        self._update_webserver_info()

        # --------------- Footer Message ---------------
        tk.Label(self.inner, text="Footer message", fg=TEXT, bg=BG, font=("Segoe UI", 11, "bold")).pack(
            anchor="w", pady=(8, 6)
        )

        self.footer = tk.Text(
            self.inner,
            height=3,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
        )
        self.footer.insert(
            "1.0",
            self.ctrl.contact_message
            or "CONTACT : CreDL MEDIA - Yoons.B1",
        )
        self.footer.pack(fill="x", pady=(0, 6))

        # --------------- 로그 구독 / 초기화 ---------------
        def _on_log(line: str):
            self._log_buffer.append(line)

        self.ctrl.subscribe_log(_on_log)
        self.after(300, self._flush_logs)

        self.refresh_lists()
        self._status_tick()

    # ----------------- 헬퍼 / 공통 -----------------
    def _toggle_log_view(self):
        """Checkbox now acts as log PLAY/PAUSE for live update.
        Layout is fixed; actual gating is handled in _flush_logs.
        """
        # Nothing to do here; we just read var_showlog in _flush_logs.
        return

    def _set_placeholder(self, entry: tk.Entry, text: str):
        entry.delete(0, "end")
        entry.insert(0, text)
        entry.config(fg="black", insertbackground="black", bg="white")

    def _flush_logs(self):
        if self._log_buffer and self.var_showlog.get():
            self.log_view.config(state="normal")
            for line in self._log_buffer:
                self.log_view.insert("end", line + "\n")
            self.log_view.see("end")
            self.log_view.config(state="disabled")
            self._log_buffer.clear()
        self.after(300, self._flush_logs)

    def _color(self, status):
        """
        상태에 따른 점 색상:
        - "on"    → 초록
        - "error" → 빨강 (연결 끊김 / 통신 오류 등)
        - 그 외   → 회색 (꺼짐, 알 수 없음 등)
        """
        if status == "on":
            return "#6dc36d"          # ON (초록)
        elif status == "error":
            return "#ef476f"          # ERROR (빨강) - 메인앱에서 쓰는 빨강과 통일
        else:
            return "#a9b2ba"          # OFF/UNKNOWN (회색)

    # ----------------- 리스트 구성 -----------------
    def refresh_lists(self):
        # PC 리스트
        for w in self.pc_container.winfo_children():
            w.destroy()
        self._pc_dots.clear()

        snap = self.ctrl.get_state_snapshot()
        pc_states = {pc["ip"]: pc.get("status", "off") for pc in snap.get("pcs", [])}

        for i, pc in enumerate(self.ctrl.config["pcs"]):
            row = tk.Frame(self.pc_container, bg=PANEL)
            row.pack(fill="x", padx=8, pady=4)

            dot = tk.Canvas(
                row,
                width=14,
                height=14,
                bg=PANEL,
                highlightthickness=0,
            )
            dot.pack(side="left", padx=(0, 6))
            c = self._color(pc_states.get(pc["ip"]))
            dot.create_oval(2, 2, 12, 12, fill=c, outline=c)
            self._pc_dots[pc["ip"]] = dot

            tk.Label(
                row,
                text=f"{pc['name']}  {pc['ip']}",
                fg=TEXT,
                bg=PANEL,
            ).pack(side="left")

            tk.Button(
                row,
                text="Edit",
                width=6,
                bg="#555",
                fg="white",
                relief="flat",
                command=lambda idx=i: self._edit_pc(idx),
            ).pack(side="right", padx=3)
            tk.Button(
                row,
                text="Delete",
                width=6,
                bg="#444",
                fg="white",
                relief="flat",
                command=lambda idx=i: self._delete_pc(idx),
            ).pack(side="right", padx=3)
            tk.Button(
                row,
                text="OFF",
                width=6,
                bg="#e76f51",
                fg="white",
                relief="flat",
                command=lambda ip=pc["ip"]: self.ctrl.run_async(
                    f"PC OFF {ip}", self.ctrl.pc_off, ip
                ),
            ).pack(side="right", padx=3)
            tk.Button(
                row,
                text="REBOOT",
                width=8,
                bg="#3f88c5",
                fg="white",
                relief="flat",
                command=lambda ip=pc["ip"]: self.ctrl.run_async(
                    f"PC REBOOT {ip}", self.ctrl.pc_reboot, ip
                ),
            ).pack(side="right", padx=3)
            tk.Button(
                row,
                text="ON",
                width=6,
                bg="#2a9d8f",
                fg="white",
                relief="flat",
                command=lambda ip=pc["ip"]: self.ctrl.run_async(
                    f"PC ON {ip}", self.ctrl.pc_on, ip
                ),
            ).pack(side="right", padx=3)

        # Projector 리스트
        for w in self.beam_container.winfo_children():
            w.destroy()
        self._beam_widgets.clear()

        beam_states = {}
        for b in snap.get("projectors", []):
            beam_states[
                (b.get("ip"), int(b.get("port", 4352)))
            ] = (b.get("status", "off"), b.get("shutter", ""))

        for i, b in enumerate(self.ctrl.config["projectors"]):
            row = tk.Frame(self.beam_container, bg=PANEL)
            row.pack(fill="x", padx=8, pady=4)

            status, shut = beam_states.get(
                (b["ip"], int(b.get("port", 4352))), ("off", "")
            )

            dot = tk.Canvas(
                row,
                width=14,
                height=14,
                bg=PANEL,
                highlightthickness=0,
            )
            dot.pack(side="left", padx=(0, 6))
            c = self._color(status)
            dot.create_oval(2, 2, 12, 12, fill=c, outline=c)

            lbl = tk.Label(
                row,
                text=f"{b['name']}  {b['ip']}:{b.get('port',4352)}"
                + (f"  [{shut.upper()}]" if shut else ""),
                fg=TEXT,
                bg=PANEL,
            )
            lbl.pack(side="left")
            self._beam_widgets[(b["ip"], int(b.get("port", 4352)))] = (dot, lbl)

            tk.Button(
                row,
                text="Edit",
                width=6,
                bg="#555",
                fg="white",
                relief="flat",
                command=lambda idx=i: self._edit_beam(idx),
            ).pack(side="right", padx=3)
            tk.Button(
                row,
                text="Delete",
                width=6,
                bg="#444",
                fg="white",
                relief="flat",
                command=lambda idx=i: self._delete_beam(idx),
            ).pack(side="right", padx=3)
            tk.Button(
                row,
                text="OPEN",
                width=7,
                bg="#3f88c5",
                fg="white",
                relief="flat",
                command=lambda ip=b["ip"], port=b.get("port", 4352): self.ctrl.run_async(
                    f"SHUTTER OPEN {ip}:{port}",
                    self.ctrl.beam_shutter_open,
                    ip,
                    port,
                ),
            ).pack(side="right", padx=3)
            tk.Button(
                row,
                text="CLOSE",
                width=7,
                bg="#ef476f",
                fg="white",
                relief="flat",
                command=lambda ip=b["ip"], port=b.get("port", 4352): self.ctrl.run_async(
                    f"SHUTTER CLOSE {ip}:{port}",
                    self.ctrl.beam_shutter_close,
                    ip,
                    port,
                ),
            ).pack(side="right", padx=3)
            tk.Button(
                row,
                text="ON",
                width=6,
                bg="#2a9d8f",
                fg="white",
                relief="flat",
                command=lambda ip=b["ip"], port=b.get("port", 4352): self.ctrl.run_async(
                    f"BEAM ON {ip}:{port}",
                    self.ctrl.beam_on,
                    ip,
                    port,
                ),
            ).pack(side="right", padx=3)
            tk.Button(
                row,
                text="OFF",
                width=6,
                bg="#e76f51",
                fg="white",
                relief="flat",
                command=lambda ip=b["ip"], port=b.get("port", 4352): self.ctrl.run_async(
                    f"BEAM OFF {ip}:{port}",
                    self.ctrl.beam_off,
                    ip,
                    port,
                ),
            ).pack(side="right", padx=3)

        # TCP 리스트
        for w in self.tcp_container.winfo_children():
            w.destroy()
        tcp_entries = self.ctrl.config.get("tcp_outputs", [])

        for idx, t in enumerate(tcp_entries):
            row = tk.Frame(self.tcp_container, bg=PANEL)
            row.pack(fill="x", padx=8, pady=4)

            lbl = tk.Label(
                row,
                text=f"{t.get('name','')}  {t.get('ip','')}:{t.get('port','')}",
                fg=TEXT,
                bg=PANEL,
            )
            lbl.pack(side="left")

            var_on = tk.BooleanVar(value=bool(t.get("use_on", True)))
            var_off = tk.BooleanVar(value=bool(t.get("use_off", True)))

            tk.Checkbutton(
                row,
                text="ON",
                variable=var_on,
                fg=TEXT,
                bg=PANEL,
                selectcolor=PANEL,
                activebackground=PANEL,
                command=lambda i=idx, v=var_on: self._toggle_tcp_flag(
                    i, "use_on", v.get()
                ),
            ).pack(side="right", padx=3)

            tk.Checkbutton(
                row,
                text="OFF",
                variable=var_off,
                fg=TEXT,
                bg=PANEL,
                selectcolor=PANEL,
                activebackground=PANEL,
                command=lambda i=idx, v=var_off: self._toggle_tcp_flag(
                    i, "use_off", v.get()
                ),
            ).pack(side="right", padx=3)

            tk.Button(
                row,
                text="Send",
                width=6,
                bg="#2a9d8f",
                fg="white",
                relief="flat",
                command=lambda i=idx: self._send_tcp_once(i),
            ).pack(side="right", padx=3)

            tk.Button(
                row,
                text="Edit",
                width=6,
                bg="#555",
                fg="white",
                relief="flat",
                command=lambda i=idx: self._edit_tcp(i),
            ).pack(side="right", padx=3)

            tk.Button(
                row,
                text="Delete",
                width=6,
                bg="#444",
                fg="white",
                relief="flat",
                command=lambda i=idx: self._delete_tcp(i),
            ).pack(side="right", padx=3)

    def _status_tick(self):
        snap = self.ctrl.get_state_snapshot()

        for pc in snap.get("pcs", []):
            ip = pc.get("ip")
            dot = self._pc_dots.get(ip)
            if dot:
                dot.delete("all")
                c = self._color(pc.get("status", "off"))
                dot.create_oval(2, 2, 12, 12, fill=c, outline=c)

        for b in snap.get("projectors", []):
            key = (b.get("ip"), int(b.get("port", 4352)))
            widgets = self._beam_widgets.get(key)
            if widgets:
                dot, lbl = widgets
                dot.delete("all")
                c = self._color(b.get("status", "off"))
                dot.create_oval(2, 2, 12, 12, fill=c, outline=c)
                sh = b.get("shutter", "")
                txt = f"{b.get('name','')}  {b.get('ip')}:{b.get('port',4352)}" + (
                    f"  [{sh.upper()}]" if sh else ""
                )
                lbl.config(text=txt)

        self.after(1000, self._status_tick)

    # ----------------- CRUD: PC -----------------
    def _read_entry(self, e: tk.Entry):
        return e.get().strip()

    def add_pc(self):
        name = self._read_entry(self.pc_name)
        ip = self._read_entry(self.pc_ip)
        mac = self._read_entry(self.pc_mac)
        port_txt = self._read_entry(self.pc_port)

        try:
            port = int(port_txt)
        except Exception:
            port = 5050

        if not name or not ip:
            messagebox.showerror("PC", "Name and IP are required.")
            return

        idx = self._pc_edit_index
        if isinstance(idx, int):
            self.ctrl.config["pcs"][idx] = {
                "name": name,
                "ip": ip,
                "mac": mac,
                "port": port,
            }
            self._pc_edit_index = None
        else:
            self.ctrl.config["pcs"].append(
                {"name": name, "ip": ip, "mac": mac, "port": port}
            )

        self.ctrl.refresh_pc_keepalives()
        self.refresh_lists()
        self.ctrl.save_config()

    def _delete_pc(self, idx: int):
        if 0 <= idx < len(self.ctrl.config["pcs"]):
            self.ctrl.config["pcs"].pop(idx)
            self.ctrl.refresh_pc_keepalives()
            self.refresh_lists()
            self.ctrl.save_config()

    def _edit_pc(self, idx: int):
        pc = self.ctrl.config["pcs"][idx]
        self.pc_name.delete(0, "end")
        self.pc_name.insert(0, pc.get("name", ""))
        self.pc_ip.delete(0, "end")
        self.pc_ip.insert(0, pc.get("ip", ""))
        self.pc_mac.delete(0, "end")
        self.pc_mac.insert(0, pc.get("mac", ""))
        self.pc_port.delete(0, "end")
        self.pc_port.insert(0, str(pc.get("port", 5050)))
        self._pc_edit_index = idx

    # ----------------- CRUD: Projector -----------------
    def add_beam(self):
        name = self._read_entry(self.b_name)
        ip = self._read_entry(self.b_ip)
        port_txt = self._read_entry(self.b_port)
        try:
            port = int(port_txt)
        except Exception:
            port = 4352
        password = self._read_entry(self.b_pass)

        if not name or not ip:
            messagebox.showerror("Projector", "Name and IP are required.")
            return

        idx = self._beam_edit_index
        if isinstance(idx, int):
            self.ctrl.config["projectors"][idx] = {
                "name": name,
                "ip": ip,
                "port": port,
                "password": password,
            }
            self._beam_edit_index = None
        else:
            self.ctrl.config["projectors"].append(
                {"name": name, "ip": ip, "port": port, "password": password}
            )

        self.ctrl.reset_beam_cache()
        self.refresh_lists()
        self.ctrl.save_config()

    def _delete_beam(self, idx: int):
        if 0 <= idx < len(self.ctrl.config["projectors"]):
            self.ctrl.config["projectors"].pop(idx)
            self.ctrl.reset_beam_cache()
            self.refresh_lists()
            self.ctrl.save_config()

    def _edit_beam(self, idx: int):
        b = self.ctrl.config["projectors"][idx]
        self.b_name.delete(0, "end")
        self.b_name.insert(0, b.get("name", ""))
        self.b_ip.delete(0, "end")
        self.b_ip.insert(0, b.get("ip", ""))
        self.b_port.delete(0, "end")
        self.b_port.insert(0, str(b.get("port", 4352)))
        self.b_pass.delete(0, "end")
        self.b_pass.insert(0, b.get("password", ""))
        self._beam_edit_index = idx

    # ----------------- CRUD: TCP -----------------
    def add_tcp(self):
        name = self._read_entry(self.tcp_name)
        ip = self._read_entry(self.tcp_ip)
        port_txt = self._read_entry(self.tcp_port)
        data = self._read_entry(self.tcp_data)

        if not name or not ip or not port_txt or not data:
            messagebox.showerror("TCP", "Name, IP, Port, Data are required.")
            return

        try:
            port = int(port_txt)
        except Exception:
            messagebox.showerror("TCP", "Port must be a number.")
            return

        entry = {
            "name": name,
            "ip": ip,
            "port": port,
            "data": data,
            "use_on": True,
            "use_off": True,
        }
        idx = self._tcp_edit_index
        if isinstance(idx, int):
            self.ctrl.config.setdefault("tcp_outputs", [])[idx] = entry
            self._tcp_edit_index = None
        else:
            self.ctrl.config.setdefault("tcp_outputs", []).append(entry)

        self.refresh_lists()
        self.ctrl.save_config()

    def _delete_tcp(self, idx: int):
        arr = self.ctrl.config.setdefault("tcp_outputs", [])
        if 0 <= idx < len(arr):
            arr.pop(idx)
            self._tcp_edit_index = None
            self.refresh_lists()
            self.ctrl.save_config()

    def _edit_tcp(self, idx: int):
        arr = self.ctrl.config.setdefault("tcp_outputs", [])
        if not (0 <= idx < len(arr)):
            return
        t = arr[idx]
        self.tcp_name.delete(0, "end")
        self.tcp_name.insert(0, t.get("name", ""))
        self.tcp_ip.delete(0, "end")
        self.tcp_ip.insert(0, t.get("ip", ""))
        self.tcp_port.delete(0, "end")
        self.tcp_port.insert(0, str(t.get("port", "")))
        self.tcp_data.delete(0, "end")
        self.tcp_data.insert(0, t.get("data", ""))
        self._tcp_edit_index = idx

    def _send_tcp_once(self, idx: int):
        arr = self.ctrl.config.get("tcp_outputs", [])
        if not (0 <= idx < len(arr)):
            return
        t = arr[idx]
        ip = t.get("ip")
        port = int(t.get("port", 0) or 0)
        data = t.get("data", "")
        if not ip or not port or not data:
            messagebox.showerror("TCP", "IP, Port, Data are required to send.")
            return

        self.ctrl.run_async(
            f"TCP SEND {ip}:{port}",
            self.ctrl._tcp_send,
            ip,
            port,
            data.encode("utf-8", errors="ignore"),
        )

    def _toggle_tcp_flag(self, idx: int, key: str, value: bool):
        arr = self.ctrl.config.setdefault("tcp_outputs", [])
        if 0 <= idx < len(arr):
            arr[idx][key] = bool(value)
            self.ctrl.save_config()

    # ----------------- OSC: 테스트 전송 -----------------
    def _send_osc_row(self, idx: int):
        if idx < 0 or idx >= len(self.osc_enable_vars):
            return

        ip = self.osc_ip_entries[idx].get().strip()
        port_txt = self.osc_port_entries[idx].get().strip()
        addr = self.osc_addr_entries[idx].get().strip()
        val = self.osc_value_entries[idx].get().strip()
        if val == "value(1,0)":
            val = ""
        vtype = self.osc_type_boxes[idx].get().strip() or "float"

        try:
            port = int(port_txt or "0")
        except Exception:
            port = 0

        if not ip or not port or not addr:
            messagebox.showerror("OSC", "IP, Port, Address는 필수입니다.")
            return

        self.ctrl.run_async(
            f"OSC TEST {idx+1}",
            self.ctrl._osc_send,
            ip,
            port,
            addr,
            val,
            vtype,
        )

    # ----------------- Save -----------------
    def save(self):
        # 스케줄
        sch_cfg = self.ctrl.config.setdefault("schedule", {})

        sch_cfg["enabled"] = self.var_schedule_enabled.get()
        sch_cfg["enabled_days"] = [v.get() for v in self.day_vars]
        sch_cfg["all_on_time"] = f"{self.on_hour.get()}:{self.on_min.get()}"
        sch_cfg["all_off_time"] = f"{self.off_hour.get()}:{self.off_min.get()}"
        sch_cfg["reboot_after_on_enabled"] = bool(self.var_reboot_after_on.get())
        try:
            rd = int(self.var_reboot_delay.get())
        except Exception:
            rd = 5
        if rd < 1:
            rd = 1
        if rd > 120:
            rd = 120
        sch_cfg["reboot_delay_min"] = rd

        # footer 메시지
        self.ctrl.contact_message = self.footer.get("1.0", "end").strip()

        # 옵션들
        aot = bool(self.var_top.get())
        shut = bool(self.var_shut.get())
        showlog = bool(self.var_showlog.get())

        self.ctrl.config["always_on_top"] = aot
        self.ctrl.config["enable_shutter_shortcut"] = shut
        self.ctrl.config["show_log_view"] = showlog

        # OSC 버튼 설정 저장
        osc_list = []
        for i in range(len(self.osc_enable_vars)):
            enabled = bool(self.osc_enable_vars[i].get())
            label = self.osc_label_entries[i].get().strip()
            ip = self.osc_ip_entries[i].get().strip()
            port_txt = self.osc_port_entries[i].get().strip()
            addr = self.osc_addr_entries[i].get().strip()
            val = self.osc_value_entries[i].get().strip()
            if val == "value(1,0)":
                val = ""
            vtype = self.osc_type_boxes[i].get().strip() or "float"
            try:
                port = int(port_txt or "0")
            except Exception:
                port = 0
            osc_list.append(
                {
                    "enabled": enabled,
                    "label": label,
                    "ip": ip,
                    "port": port,
                    "address": addr,
                    "value": val,
                    "type": vtype,
                }
            )
        self.ctrl.config["osc_buttons"] = osc_list

        # OSC 슬라이더 설정 저장
        slider_list = []
        old_sliders = self.ctrl.config.get("osc_sliders", [])

        for i in range(len(self.slider_enable_vars)):
            enabled = bool(self.slider_enable_vars[i].get())
            label = self.slider_label_entries[i].get().strip()
            ip = self.slider_ip_entries[i].get().strip()
            port_txt = self.slider_port_entries[i].get().strip()
            addr = self.slider_addr_entries[i].get().strip()
            min_txt = self.slider_min_entries[i].get().strip()
            max_txt = self.slider_max_entries[i].get().strip()
            vtype = self.slider_type_boxes[i].get().strip() or "float"

            try:
                port = int(port_txt or "0")
            except Exception:
                port = 0
            try:
                vmin = int(min_txt or "0")
            except Exception:
                vmin = 0
            try:
                vmax = int(max_txt or "0")
            except Exception:
                vmax = vmin + 1

            # 기존에 저장된 current 값이 있으면 그대로 유지
            current_val = None
            if 0 <= i < len(old_sliders):
                try:
                    current_val = float(old_sliders[i].get("current", None))
                except Exception:
                    current_val = None

            entry = {
                "enabled": enabled,
                "label": label,
                "ip": ip,
                "port": port,
                "address": addr,
                "min": vmin,
                "max": vmax,
                "type": vtype,
            }
            if current_val is not None:
                entry["current"] = current_val

            slider_list.append(entry)

        self.ctrl.config["osc_sliders"] = slider_list

        # Always on top 반영
        try:
            if self.root_ref is not None:
                self.root_ref.attributes("-topmost", aot)
        except Exception:
            pass

        if self.main_ref is not None:
            self.main_ref.set_shutter_enabled(shut)
            try:
                self.main_ref.update_idletasks()
            except Exception:
                pass
            self.main_ref.refresh_footer()
            try:
                self.main_ref.refresh_osc_buttons()
                self.main_ref.refresh_osc_sliders()
            except Exception:
                pass

        # 스케줄이 변경되었을 수 있으므로, AutoScheduler 하루 1회 실행 기록 리셋
        sched = getattr(self.ctrl, "scheduler", None)
        if sched and hasattr(sched, "reset_fired_dates"):
            try:
                sched.reset_fired_dates()
            except Exception as e:
                self.ctrl.log(f"Scheduler reset error (settings): {e}")

        self.ctrl.save_config()
        messagebox.showinfo("Saved", "Settings saved.")
