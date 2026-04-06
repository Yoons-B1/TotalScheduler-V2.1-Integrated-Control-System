import tkinter as tk

BG = "#111315"
PANEL = "#171a1d"
ACCENT = "#2a9d8f"
TEXT = "#e8e8e8"
SUBTEXT = "#a9b2ba"
ERR = "#e76f51"

BTN_W = 18
BTN_H = 3

OSC_COLOR = "#f4a261"  # OSC 버튼 색상 (기존과 다른 색)


class MainPage(tk.Frame):
    def __init__(self, master, ctrl, on_open_settings):
        super().__init__(master, bg=BG)
        self.ctrl = ctrl
        self.on_open_settings = on_open_settings
        self._last_pc_sig = None
        self._last_beam_sig = None
        self._open_btn = None
        self._close_btn = None
        self._shutter_bound = False
        self._osc_sig = None      # OSC 버튼 구성 시그니처
        self._slider_sig = None   # OSC 슬라이더 구성 시그니처

        # ----------------- 헤더 -----------------
        header = tk.Frame(self, bg=BG)
        # 위쪽 여백 조금 줄이고 전체를 살짝 위로
        header.pack(fill="x", pady=(6, 4))
        tk.Label(
            header,
            text=self.ctrl.app_name,
            fg=TEXT,
            bg=BG,
            font=("Segoe UI", 22, "bold"),
        ).pack(anchor="center")
        tk.Button(
            header,
            text="Setup",
            bg=ACCENT,
            fg="white",
            relief="flat",
            width=9,
            height=1,   # 버튼을 살짝 작게
            command=on_open_settings,
        ).pack(side="right", padx=16)

        # ----------------- 바디 -----------------
        body = tk.Frame(self, bg=BG)
        # 세로 여백을 조금 줄여서 전체를 위로
        body.pack(fill="both", expand=True, padx=12, pady=4)

        # 왼쪽: 제어 버튼들
        left_controls = tk.Frame(body, bg=BG)
        left_controls.pack(side="left", fill="y", padx=(0, 8))

        # 1줄: ALL ON / ALL OFF
        r1 = tk.Frame(left_controls, bg=BG)
        r1.pack(pady=8)
        tk.Button(
            r1,
            text="ALL ON",
            width=BTN_W,
            height=BTN_H,
            bg=ACCENT,
            fg="white",
            relief="flat",
            command=lambda: self.ctrl.run_async("ALL ON", self.ctrl.all_on),
        ).pack(side="left", padx=8)
        tk.Button(
            r1,
            text="ALL OFF",
            width=BTN_W,
            height=BTN_H,
            bg=ERR,
            fg="white",
            relief="flat",
            command=lambda: self.ctrl.run_async("ALL OFF", self.ctrl.all_off),
        ).pack(side="left", padx=8)

        # 2줄: PC 그룹
        r2 = tk.Frame(left_controls, bg=BG)
        r2.pack(pady=8)
        tk.Button(
            r2,
            text="PC ON",
            width=BTN_W,
            height=BTN_H,
            bg=ACCENT,
            fg="white",
            relief="flat",
            command=lambda: self.ctrl.run_async("PC GROUP ON", self.ctrl.group_pc_on),
        ).pack(side="left", padx=8)
        tk.Button(
            r2,
            text="PC OFF",
            width=BTN_W,
            height=BTN_H,
            bg=ERR,
            fg="white",
            relief="flat",
            command=lambda: self.ctrl.run_async("PC GROUP OFF", self.ctrl.group_pc_off),
        ).pack(side="left", padx=8)

        # 3줄: BEAM 그룹
        r3 = tk.Frame(left_controls, bg=BG)
        r3.pack(pady=8)
        tk.Button(
            r3,
            text="BEAM ON",
            width=BTN_W,
            height=BTN_H,
            bg=ACCENT,
            fg="white",
            relief="flat",
            command=lambda: self.ctrl.run_async("BEAM GROUP ON", self.ctrl.group_beam_on),
        ).pack(side="left", padx=8)
        tk.Button(
            r3,
            text="BEAM OFF",
            width=BTN_W,
            height=BTN_H,
            bg=ERR,
            fg="white",
            relief="flat",
            command=lambda: self.ctrl.run_async("BEAM GROUP OFF", self.ctrl.group_beam_off),
        ).pack(side="left", padx=8)

        # 4줄: SHUTTER (설정에 따라 표시)  ← ★ OSC보다 위에
        self.r4 = tk.Frame(left_controls, bg=BG)
        self._open_btn = tk.Button(
            self.r4,
            text="SHUTTER OPEN  →",
            width=BTN_W,
            height=BTN_H,
            bg="#3f88c5",
            fg="white",
            relief="flat",
            command=lambda: self.ctrl.run_async("SHUTTER OPEN ALL", self.ctrl.group_shutter_open),
        )
        self._open_btn.pack(side="left", padx=8)
        self._close_btn = tk.Button(
            self.r4,
            text="SHUTTER CLOSE ←",
            width=BTN_W,
            height=BTN_H,
            bg="#ef476f",
            fg="white",
            relief="flat",
            command=lambda: self.ctrl.run_async("SHUTTER CLOSE ALL", self.ctrl.group_shutter_close),
        )
        self._close_btn.pack(side="left", padx=8)

        # 5줄: OSC 버튼 영역 (기본 버튼들 + 셔터 아래)
        self.osc_frame = tk.Frame(left_controls, bg=BG)
        self.osc_frame.pack(fill="x", pady=(16, 0))

        # 6줄: OSC 슬라이더 2줄
        self.slider_frame = tk.Frame(left_controls, bg=BG)
        self.slider_frame.pack(fill="x", pady=(12, 0))

        # 오른쪽: 상태 리스트
        right_status = tk.Frame(body, bg=BG)
        right_status.pack(side="left", fill="both", expand=True)

        tk.Label(right_status, text="PCs", fg=TEXT, bg=BG).pack(anchor="w")
        self.pc_list = tk.Frame(
            right_status,
            bg=PANEL,
            highlightbackground="#0d0f12",
            highlightthickness=1,
        )
        self.pc_list.pack(fill="both", expand=True, pady=(4, 10))

        tk.Label(right_status, text="Projectors", fg=TEXT, bg=BG).pack(anchor="w")
        self.beam_list = tk.Frame(
            right_status,
            bg=PANEL,
            highlightbackground="#0d0f12",
            highlightthickness=1,
        )
        self.beam_list.pack(fill="both", expand=True, pady=(4, 10))

        # ----------------- 푸터 -----------------
        footer = tk.Frame(self, bg=BG)
        footer.pack(fill="x", side="bottom", pady=(6, 12))
        self.time_label = tk.Label(footer, text="", fg=SUBTEXT, bg=BG)
        self.time_label.pack(side="left", padx=16)
        self.msg_label = tk.Label(
            footer,
            text=self.ctrl.contact_message,
            fg=SUBTEXT,
            bg=BG,
        )
        self.msg_label.pack(side="right", padx=16)

        # ALL ON/OFF 동작 중일 때 덮어주는 오버레이
        self.overlay = tk.Label(
            self,
            text="Running... Please wait",
            fg="white",
            bg="#000000",
            font=("Segoe UI", 20, "bold"),
        )
        self.overlay.place_forget()

        # 초기 상태 반영
        self.enforce_shutter_from_config()
        self.refresh_osc_buttons()
        self.refresh_osc_sliders()

        self._tick()

    # --------------------------------------------------
    # 공통 / 헬퍼
    # --------------------------------------------------
    def refresh_footer(self):
        self.msg_label.config(text=self.ctrl.contact_message)

    def _flash_button(self, btn):
        if not btn:
            return
        try:
            btn.config(relief="sunken")
            self.after(120, lambda: btn.config(relief="flat"))
        except Exception:
            pass

    # 키보드 ← → 로 셔터 제어
    def _bind_shutter_keys(self, enable: bool):
        if enable and not self._shutter_bound:
            self.bind_all("<Right>", self._on_right)
            self.bind_all("<Left>", self._on_left)
            self._shutter_bound = True
        elif not enable and self._shutter_bound:
            self.unbind_all("<Right>")
            self.unbind_all("<Left>")
            self._shutter_bound = False

    def _on_right(self, e):
        self._flash_button(self._open_btn)
        self.ctrl.run_async("SHUTTER OPEN ALL", self.ctrl.group_shutter_open)

    def _on_left(self, e):
        self._flash_button(self._close_btn)
        self.ctrl.run_async("SHUTTER CLOSE ALL", self.ctrl.group_shutter_close)

    def set_shutter_enabled(self, enabled: bool):
        if enabled:
            if not self.r4.winfo_manager():
                # ★ 항상 OSC 버튼보다 위에 오도록 before=self.osc_frame 사용
                self.r4.pack(pady=8, before=self.osc_frame)
            self._bind_shutter_keys(True)
        else:
            if self.r4.winfo_manager():
                self.r4.pack_forget()
            self._bind_shutter_keys(False)
        try:
            self.focus_force()
        except Exception:
            pass

    def enforce_shutter_from_config(self):
        self.set_shutter_enabled(bool(self.ctrl.config.get("enable_shutter_shortcut", False)))

    # --------------------------------------------------
    # OSC 버튼 영역
    # --------------------------------------------------
    def _osc_signature(self):
        buttons = self.ctrl.config.get("osc_buttons", [])
        # enabled + label 기준으로 바뀌었는지 체크
        return tuple((bool(b.get("enabled")), b.get("label", "")) for b in buttons)

    def refresh_osc_buttons(self):
        sig = self._osc_signature()
        if sig == self._osc_sig:
            return
        self._osc_sig = sig

        # 기존 버튼 제거
        for w in self.osc_frame.winfo_children():
            w.destroy()

        buttons = self.ctrl.config.get("osc_buttons", [])
        enabled_list = [(idx, b) for idx, b in enumerate(buttons) if b.get("enabled")]
        if not enabled_list:
            return

        per_row = 3
        row = None
        for i, (idx, cfg) in enumerate(enabled_list):
            if i % per_row == 0:
                row = tk.Frame(self.osc_frame, bg=BG)
                row.pack(anchor="w", pady=4)  # 세로 간격

            label = cfg.get("label") or f"OSC {idx+1}"
            btn = tk.Button(
                row,
                text=label,
                width=12,   # 살짝 줄인 폭
                height=2,
                bg=OSC_COLOR,
                fg="black",
                relief="raised",
            )
            # 버튼 간 간격 넓게 (Surface Go 3 터치 고려)
            btn.pack(side="left", padx=10, pady=2)

            # 마우스/터치 누름/뗌에 따라 press/release 전송
            btn.bind(
                "<ButtonPress-1>",
                lambda e, j=idx: self.ctrl.run_async(
                    f"OSC {j+1} DOWN",
                    self.ctrl.send_osc_index,
                    j,
                    "press",
                ),
            )
            btn.bind(
                "<ButtonRelease-1>",
                lambda e, j=idx: self.ctrl.run_async(
                    f"OSC {j+1} UP",
                    self.ctrl.send_osc_index,
                    j,
                    "release",
                ),
            )

    # --------------------------------------------------
    # OSC 슬라이더 영역 (2줄)
    # --------------------------------------------------
    def _slider_signature(self):
        sliders = self.ctrl.config.get("osc_sliders", [])
        return tuple(
            (
                bool(s.get("enabled")),
                s.get("label", ""),
                s.get("ip", ""),
                s.get("port", 0),
                s.get("address", ""),
                s.get("min", 0),
                s.get("max", 100),
                s.get("type", "float"),
            )
            for s in sliders
        )

    def refresh_osc_sliders(self):
        sig = self._slider_signature()
        if sig == self._slider_sig:
            return
        self._slider_sig = sig

        # 기존 위젯 제거
        for w in self.slider_frame.winfo_children():
            w.destroy()

        sliders = self.ctrl.config.get("osc_sliders", [])
        enabled_list = [(idx, s) for idx, s in enumerate(sliders) if s.get("enabled")]
        if not enabled_list:
            return

        # 각 슬라이더: 위에 제목, 아래 한 줄에 [값 0~100] [슬라이더 트랙]
        for idx, cfg in enabled_list:
            outer = tk.Frame(self.slider_frame, bg=BG)
            outer.pack(fill="x", pady=6)

            # ─ 제목 (예: Main Opacity / Main Volume)
            label = cfg.get("label") or f"SLIDER {idx+1}"
            tk.Label(outer, text=label, fg=TEXT, bg=BG).pack(
                anchor="w", padx=4
            )

            # ─ 값 + 슬라이더 한 줄
            row = tk.Frame(outer, bg=BG)
            row.pack(fill="x", pady=(2, 0))

            vtype = (cfg.get("type", "float") or "float").lower()

            # min / max
            try:
                vmin = float(cfg.get("min", 0.0))
            except Exception:
                vmin = 0.0
            try:
                vmax = float(cfg.get("max", 1.0))
            except Exception:
                vmax = 1.0
            if vmin == vmax:
                vmax = vmin + 1.0

            # --- 저장된 current 값 있으면 그 값 사용, 없으면 가운데 값 ---
            stored = cfg.get("current", None)
            if stored is not None:
                try:
                    default = float(stored)
                except Exception:
                    default = (vmin + vmax) / 2.0
            else:
                default = (vmin + vmax) / 2.0

            # 0~100 표시용 라벨 변수 (슬라이더 왼쪽)
            value_var = tk.StringVar()
            value_var.set(self._format_slider_value(default, vmin, vmax))

            val_label = tk.Label(
                row,
                textvariable=value_var,
                fg=TEXT,
                bg=BG,
                width=4,
                anchor="w",
            )
            val_label.pack(side="left", padx=4)

            # ─ 흰색 테두리 박스(트랙)
            track_frame = tk.Frame(
                row,
                bg="#ffffff",          # 흰색 테두리
                highlightthickness=0,
            )
            track_frame.pack(side="left", fill="x", expand=True, padx=(4, 8))

            # 내부 실제 트랙(밝은 회색)
            inner_track = tk.Frame(
                track_frame,
                bg="#2b3137",          # 트랙 색
                height=28,             # 트랙 높이
            )
            inner_track.pack(fill="x", expand=True, padx=1, pady=1)

            # 해상도: float → 0.01, int → 1
            if vtype == "int":
                resolution = 1
            else:
                resolution = 0.01

            # ─ 실제 슬라이더 (손잡이 기본 흰색, 누르면 청록색)
            scale = tk.Scale(
                inner_track,
                from_=vmin,
                to=vmax,
                orient=tk.HORIZONTAL,
                length=320,
                bg="#ffffff",                 # 손잡이 기본색
                fg=TEXT,
                troughcolor="#2b3137",
                highlightthickness=0,
                showvalue=False,
                resolution=resolution,
                bd=0,
                relief="flat",
                sliderrelief="flat",
                activebackground=ACCENT,      # 누르면 청록색
                width=24,                     # 슬라이더 세로 두께
            )
            scale.set(default)
            scale.pack(fill="x", expand=True, padx=0, pady=0)

            # 슬라이더를 움직이는 동안 값 갱신 + OSC 실시간 전송
            def _on_move(val, j=idx, vmin_local=vmin, vmax_local=vmax, var=value_var):
                try:
                    v = float(val)
                except Exception:
                    return
                # 표시용 0~100 갱신
                var.set(self._format_slider_value(v, vmin_local, vmax_local))
                # OSC 전송 (실제 값: vmin~vmax 범위)
                self._send_slider_value(j, v)

            scale.configure(command=_on_move)

            # 마우스/터치에서 손을 뗄 때 현재 값을 config에 저장
            def _on_release(event, j=idx, s=scale):
                val = s.get()
                self._update_slider_current(j, val)

            scale.bind("<ButtonRelease-1>", _on_release)

    def _format_slider_value(self, v, vmin: float, vmax: float):
        """
        실제 값(v, vmin~vmax 범위)을 0~100 사이 정수 문자열로 변환.
        """
        try:
            fv = float(v)
        except Exception:
            return "0"
        if vmax == vmin:
            return "0"
        norm = (fv - vmin) / (vmax - vmin)
        if norm < 0:
            norm = 0.0
        if norm > 1:
            norm = 1.0
        display = norm * 100.0
        return f"{display:.0f}"

    def _send_slider_value(self, idx: int, value):
        sliders = self.ctrl.config.get("osc_sliders", [])
        if not (0 <= idx < len(sliders)):
            return
        cfg = sliders[idx]
        ip = (cfg.get("ip", "") or "").strip()
        port = cfg.get("port", 0)
        addr = (cfg.get("address", "") or "").strip()
        vtype = cfg.get("type", "float") or "float"

        try:
            port = int(port or 0)
        except Exception:
            port = 0

        if not ip or not port or not addr:
            self.ctrl.log(f"OSC Slider {idx+1} invalid config; skip.")
            return

        # run_async를 통해 백그라운드에서 전송
        self.ctrl.run_async(
            f"OSC SLIDER {idx+1}",
            self.ctrl._osc_send,
            ip,
            port,
            addr,
            value,
            vtype,
        )

    def _update_slider_current(self, idx: int, value):
        """
        현재 슬라이더 값을 config에 기록하고 저장.
        """
        sliders = self.ctrl.config.setdefault("osc_sliders", [])
        if 0 <= idx < len(sliders):
            try:
                sliders[idx]["current"] = float(value)
            except Exception:
                return
            # 슬라이더 움직임이 끝났을 때만 저장하므로 부담 적음
            try:
                self.ctrl.save_config()
            except Exception:
                self.ctrl.log(f"Failed to save slider {idx+1} value.")

    # --------------------------------------------------
    # 상태 표시 / 공통 UI
    # --------------------------------------------------
    def _color_dot(self, status):
        return {
            "on": "#6dc36d",
            "off": "#a9b2ba",
            "error": "#e76f51",
        }.get(status, "#a9b2ba")

    def _sig_pcs(self, items):
        return tuple(
            (i.get("name"), i.get("ip"), i.get("status")) for i in items
        )

    def _sig_beams(self, items):
        return tuple(
            (
                i.get("name"),
                i.get("ip"),
                i.get("port", 4352),
                i.get("status"),
                i.get("shutter", ""),
            )
            for i in items
        )

    def _fill_pcs(self, items):
        for w in self.pc_list.winfo_children():
            w.destroy()
        cols = 2 if len(items) > 8 else 1
        col_frames = []
        for _ in range(cols):
            f = tk.Frame(self.pc_list, bg=PANEL)
            f.pack(side="left", fill="both", expand=True, padx=4)
            col_frames.append(f)
        per_col = (len(items) + cols - 1) // cols if cols else len(items)
        for idx, item in enumerate(items):
            col = idx // per_col if per_col else 0
            f = col_frames[col]
            row = tk.Frame(f, bg=PANEL)
            row.pack(fill="x", padx=8, pady=3)
            dot = tk.Canvas(
                row,
                width=14,
                height=14,
                bg=PANEL,
                highlightthickness=0,
            )
            dot.pack(side="left")
            color = self._color_dot(item.get("status"))
            dot.create_oval(2, 2, 12, 12, fill=color, outline=color)
            tk.Label(
                row,
                text=f"{item.get('name','?')}  {item.get('ip','?')}",
                fg=TEXT,
                bg=PANEL,
            ).pack(side="left", padx=6)

    def _fill_beams(self, items):
        for w in self.beam_list.winfo_children():
            w.destroy()
        cols = 2 if len(items) > 12 else 1
        col_frames = []
        for _ in range(cols):
            f = tk.Frame(self.beam_list, bg=PANEL)
            f.pack(side="left", fill="both", expand=True, padx=4)
            col_frames.append(f)
        per_col = (len(items) + cols - 1) // cols if cols else len(items)
        for idx, item in enumerate(items):
            col = idx // per_col if per_col else 0
            f = col_frames[col]
            row = tk.Frame(f, bg=PANEL)
            row.pack(fill="x", padx=8, pady=3)
            dot = tk.Canvas(
                row,
                width=14,
                height=14,
                bg=PANEL,
                highlightthickness=0,
            )
            dot.pack(side="left")
            color = self._color_dot(item.get("status"))
            dot.create_oval(2, 2, 12, 12, fill=color, outline=color)
            name = item.get("name", "?")
            ip = item.get("ip", "?")
            port = item.get("port", 4352)
            sh = item.get("shutter", "")
            sh_txt = f"  [{sh.upper()}]" if sh else ""
            tk.Label(
                row,
                text=f"{name}  {ip}:{port}{sh_txt}",
                fg=TEXT,
                bg=PANEL,
            ).pack(side="left", padx=6)

    def _tick(self):
        import datetime

        self.time_label.config(
            text=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        self.msg_label.config(text=self.ctrl.contact_message)

        # 셔터 & 숏컷 옵션 반영
        self.set_shutter_enabled(
            bool(self.ctrl.config.get("enable_shutter_shortcut", False))
        )

        snap = self.ctrl.get_state_snapshot()
        pcs = snap.get("pcs", [])
        beams = snap.get("projectors", [])

        pc_sig = self._sig_pcs(pcs)
        if pc_sig != self._last_pc_sig:
            self._fill_pcs(pcs)
            self._last_pc_sig = pc_sig

        beam_sig = self._sig_beams(beams)
        if beam_sig != self._last_beam_sig:
            self._fill_beams(beams)
            self._last_beam_sig = beam_sig

        busy, name = self.ctrl.is_busy()
        if busy and str(name).upper().startswith("ALL"):
            self.overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.overlay.lift()
            self.overlay.config(text=f"Running... {name}")
        else:
            self.overlay.place_forget()

        # 설정이 바뀌었을 수도 있으니 주기적으로 체크
        self.refresh_osc_buttons()
        self.refresh_osc_sliders()

        self.after(1000, self._tick)
