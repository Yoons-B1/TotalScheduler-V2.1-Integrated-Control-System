import os, sys, json, threading, time, socket, queue, struct
from scheduler import AutoScheduler
from pjlink import PJLink
import requests

class AppState(dict): pass

class _TCPKeeper(threading.Thread):
    def __init__(self, ip, port, stop_event, log_cb=None):
        super().__init__(daemon=True)
        self.ip = ip; self.port = port
        self._external_stop = stop_event
        self._log = log_cb or (lambda m: None)
        self.sock = None
        self.is_connected = False
        self._local_stop = threading.Event()
        self.initial_probe_complete = False  # 프로그램 처음 실행 시 알림 방지용

    def stop(self):
        self._local_stop.set()
        try:
            if self.sock:
                try: self.sock.shutdown(socket.SHUT_RDWR)
                except Exception: pass
                self.sock.close()
        except: pass

    def run(self):
        while not self._external_stop.is_set() and not self._local_stop.is_set():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2.0)
                s.connect((self.ip, self.port))
                self.sock = s
                self.is_connected = True
                self._log(f"Keepalive connected {self.ip}:{self.port}")
                last = 0
                while not self._external_stop.is_set() and not self._local_stop.is_set():
                    now = time.time()
                    if now - last > 300:
                        try: s.sendall(b"ping\n")
                        except Exception as e:
                            self._log(f"Keepalive ping failed {self.ip}:{self.port} -> {e}")
                            break
                        last = now
                    time.sleep(1)
            except Exception as e:
                if self._local_stop.is_set() or self._external_stop.is_set():
                    break
                self._log(f"Keepalive error {self.ip}:{self.port} -> {e}")
                time.sleep(2)
            finally:
                try:
                    if self.sock:
                        try: self.sock.shutdown(socket.SHUT_RDWR)
                        except Exception: pass
                        self.sock.close()
                except: pass
                self.sock = None
                if self.is_connected:
                    self._log(f"Keepalive closed {self.ip}:{self.port}")
                self.is_connected = False

class Controller:
    def send_telegram_alert(self, text: str):
        """
        텔레그램으로 오류 알림을 보내는 헬퍼.
        config.json에 telegram_bot_token, telegram_chat_id가 없으면 조용히 무시.
        """
        try:
            # 최근 몇 초 안에 같은 메시지를 이미 보냈다면 중복 방지
            now = time.time()
            if (
                getattr(self, "_last_telegram_text", None) == text
                and (now - getattr(self, "_last_telegram_time", 0.0)) < 3.0
            ):
                return
            self._last_telegram_text = text
            self._last_telegram_time = now

            token = self.config.get("telegram_bot_token")
            chat_id = self.config.get("telegram_chat_id")
            if not token or not chat_id:
                return  # 설정 안 되어 있으면 아무것도 안 함

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
            requests.post(url, data=data, timeout=5)
        except Exception as e:
            # 텔레그램 실패로 전체 앱이 죽지 않도록, 로그만 남김
            self.log(f"Telegram alert failed: {e}")

    def __init__(self, app_name: str, author: str):
        self.app_name = app_name
        self.author = author
        self.base_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
        self.config_dir = os.path.join(self.base_dir, ".config")
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_path = os.path.join(self.config_dir, "config.json")

        # 로그 디렉터리 (.config/logs)
        self.log_dir = os.path.join(self.config_dir, "logs")
        os.makedirs(self.log_dir, exist_ok=True)

        self.beam_error_flags = {}
        self.pc_error_flags = {}
        self.tcp_error_flags = {}

        # 프로젝터 전원/PC 제어 직후, BEAM 에러 알림을 잠시 무시하기 위한 grace window
        # key: "ip:port" -> timestamp (time.time())
        self.beam_transition_until = {}

        # 우리가 직접 PC에 shutdown/reboot 명령을 보낸 상태인지 표시
        self.pc_shutdown_pending = {}

        # PC에 대해 우리가 shutdown/reboot 명령을 보낸 직후,
        # 일정 시간(예: 60초) 동안은 비정상 종료로 보지 않기 위한 grace window
        # key: "ip:port" -> timestamp (time.time())
        self.pc_expected_off_until = {}

        # RemotePower 모니터링 최초 1회 여부 (앱 처음 켜졌을 때 알림 방지용)
        self.initial_probe_complete = False

        # 텔레그램 중복 방지용
        self._last_telegram_text = None
        self._last_telegram_time = 0.0

        # --- 첫 실행 여부 체크 (config.json이 존재했는지) ---
        existed = os.path.exists(self.config_path)

        # 설정 로드 / 기본 생성
        self.config = self._load_or_create_default()

        # WebUI port 기본값
        if "web_port" not in self.config:
            self.config["web_port"] = 9999

        self.web_server_ok = False


        # 첫 실행이면 True, 아니면 False
        self.first_run = not existed

        if "tcp_outputs" not in self.config:
            self.config["tcp_outputs"] = []

        # OSC 버튼 설정 기본값
        if "osc_buttons" not in self.config:
            self.config["osc_buttons"] = []

        # OSC 슬라이더 설정 기본값 (없으면 빈 리스트)
        if "osc_sliders" not in self.config:
            self.config["osc_sliders"] = []

        self.contact_message = self.config.get(
            "contact_message",
            "CONTACT : CreDL MEDIA - Yoons.B1",
        )

        self.web_group_title = self.config.get(
            "web_group_title",
            "Group Control",
        )

        self.state_lock = threading.Lock()
        self.state = AppState(pcs=[], projectors=[])

        self._stop = threading.Event()

        self._log_listeners = []
        self._log_queue = queue.Queue()
        self._log_ring = []  # WebUI에서 최근 로그 조회용 (메모리 버퍼)

        self._op_lock = threading.Lock()
        self._op_running = False
        self._op_name = ""

        self._keepers = {}

        self._last_pc_poll = 0.0
        self._last_beam_poll = 0.0
        self._beam_idx = 0

        self._need_shutter_probe = set()

        # NEW: offline override map (ip -> expiry ts)
        self._pc_offline_override = {}

        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.log_thread = threading.Thread(target=self._log_dispatch_loop, daemon=True)
        self.log_thread.start()

        self.scheduler = AutoScheduler(self)
        self.scheduler.start()

        self.refresh_pc_keepalives()
        self.request_shutter_probe_all()
        self.log("Controller ready.")

    def reset_schedule_fired_dates(self):
        """스케줄이 변경될 때 AutoScheduler의 '하루 1회 실행' 기록을 리셋."""
        try:
            if hasattr(self, "scheduler") and self.scheduler is not None:
                self.scheduler.reset_fired_dates()
        except Exception as e:
            self.log(f"[Scheduler] reset_fired_dates failed: {e}")
            
    def reset_beam_cache(self):
        with self.state_lock:
            self.state["projectors"] = []
        self._beam_idx = 0
        self.request_shutter_probe_all()
        self.log("Beam state cache reset.")

    def subscribe_log(self, fn):
        if fn not in self._log_listeners:
            self._log_listeners.append(fn)

    def log(self, msg: str):
        import time as _t
        ts = _t.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        # Enqueue for Tk log listeners
        self._log_queue.put(line)
        # Keep a small in-memory ring buffer for WebUI
        try:
            self._log_ring.append(line)
            # Keep only the latest 500 lines
            if len(self._log_ring) > 500:
                self._log_ring = self._log_ring[-500:]
        except Exception:
            # In case _log_ring is not initialized for some reason
            self._log_ring = [line]

        # ✅ [DEBUG] 로그는 파일에는 남기지 않고,
        #    화면(Tk 로그창)과 WebUI에만 남긴다.
        if msg.startswith("[DEBUG]") or msg.startswith("DEBUG:"):
            return

        # --- 파일 로그 기록 (날짜별) ---
        try:
            date_str = _t.strftime("%Y-%m-%d")
            filename = f"TotalScheduler_{date_str}.log"
            path = os.path.join(self.log_dir, filename)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

            # 최대 5일치 로그만 유지
            try:
                files = sorted(
                    fn for fn in os.listdir(self.log_dir)
                    if fn.startswith("TotalScheduler_") and fn.endswith(".log")
                )
                while len(files) > 5:
                    old = files.pop(0)
                    try:
                        os.remove(os.path.join(self.log_dir, old))
                    except Exception:
                        pass
            except Exception:
                # 정리 실패해도 전체 동작에는 영향 없음
                pass
        except Exception:
            # 파일 로그에서 에러가 나도 전체 앱이 죽지 않도록 무시
            pass

    def _log_dispatch_loop(self):
        while not self._stop.is_set():
            try: line = self._log_queue.get(timeout=0.5)
            except queue.Empty: continue
            for fn in list(self._log_listeners):
                try: fn(line)
                except Exception: pass

    def get_recent_logs(self, limit: int = 100):
        """Return the latest N log lines for WebUI."""
        try:
            return self._log_ring[-limit:]
        except Exception:
            return []


    def _load_or_create_default(self):
        if not os.path.exists(self.config_path):
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({
                    "pcs": [],
                    "projectors": [],
                    "tcp_outputs": [],
                    "schedule": {
                        "enabled": True,
                        "enabled_days": [True, True, True, True, True, True, False],
                        "all_on_time": "09:00",
                        "all_off_time": "18:00"
                    },
                    "monitor_interval_sec": 3,
                    "sequential_delay_sec": 1,
                    "wol_repeat": 2,   # ★ PC마다 WOL 기본 2회 전송
                    "between_group_delay_sec": 5,
                    "always_on_top": False,
                    "enable_shutter_shortcut": False,
                    "show_log_view": True,
                    "contact_message": "CONTACT : CreDL MEDIA · Yoons.B1",
                    "web_group_title": "Group Control"
                }, f, ensure_ascii=False, indent=2)
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_config(self):
        self.config["contact_message"] = self.contact_message
        self.config["web_group_title"] = self.web_group_title
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
        self.log("Config saved.")

    def request_shutter_probe_all(self):
        self._need_shutter_probe = set((b.get("ip"), int(b.get("port",4352))) for b in self.config.get("projectors", []))

    def get_state_snapshot(self):
        with self.state_lock:
            return {"pcs": list(self.state["pcs"]), "projectors": list(self.state["projectors"])}

    def is_busy(self):
        with self._op_lock:
            return self._op_running, self._op_name

    def run_async(self, name: str, func, *args, **kwargs):
        def _wrapper():
            with self._op_lock:
                if self._op_running:
                    self.log(f"Skipped '{name}'; running: {self._op_name}")
                    return
                self._op_running = True
                self._op_name = name
            try:
                self.log(f"START {name}")
                func(*args, **kwargs)
                self.log(f"DONE {name}")
            except Exception as e:
                self.log(f"ERROR {name} -> {e}")
            finally:
                with self._op_lock:
                    self._op_running = False
                    self._op_name = ""
        threading.Thread(target=_wrapper, daemon=True).start()

    def shutdown(self):
        self._stop.set()
        self.scheduler.stop()
        for k in list(self._keepers.values()): k.stop()
        self._keepers.clear()
        self.log("Controller shutdown.")

    def refresh_pc_keepalives(self):
        """
        예전 버전에서는 PC 상태를 TCP keepalive 스레드로 관리했지만,
        현재 버전에서는 RemotePower.exe(5050 포트)에 대한
        주기적인 빠른 probe(_quick_pc_probe_once)만 사용한다.

        따라서 이 함수는 더 이상 아무 것도 하지 않는다.
        (호출해도 부작용 없음)
        """
        return

    def _set_beam_transition_for_all_beams(self, grace_sec: float = None):
        """
        BEAM 전원 상태와 직접 관계는 없지만,
        PC ON/OFF 등의 동작 중에 일시적인 네트워크 부하로 PJLink 폴링이 실패해도
        텔레그램 BEAM 에러 알림이 쏟아지지 않도록 grace window를 설정한다.
        """
        try:
            if grace_sec is None:
                grace_sec = float(self.config.get("beam_transition_grace_sec", 90.0))
        except Exception:
            grace_sec = 90.0

        deadline = time.time() + grace_sec
        for b in self.config.get("projectors", []):
            host = b.get("ip")
            port = int(b.get("port", 4352))
            key = f"{host}:{port}"
            self.beam_transition_until[key] = deadline

    # ---- GROUP OPERATIONS ----
    def all_on(self):
        """
        ALL ON 순서:
          1) BEAM 순차 ON
          2) 5초 대기
          3) TCP 버튼 순차 ON
          4) 15초 대기
          5) PC 순차 ON
        """
        delay_beam_tcp = self.config.get("between_beam_tcp_delay_sec", 5)
        delay_tcp_pc   = self.config.get("between_tcp_pc_delay_sec", 15)

        # 1) 프로젝터 순차 ON
        self.group_beam_on()

        # 2) BEAM → TCP 사이 대기
        time.sleep(delay_beam_tcp)

        # 3) TCP 출력 순차 ON
        self.group_tcp_on()

        # 4) TCP → PC 사이 대기
        time.sleep(delay_tcp_pc)

        # 5) PC 순차 ON
        self.group_pc_on()

    def all_off(self):
        """
        ALL OFF 순서 (ALL ON의 반대):
          1) PC 순차 OFF
          2) 15초 대기
          3) TCP 버튼 순차 OFF
          4) 5초 대기
          5) BEAM 순차 OFF
        """
        delay_beam_tcp = self.config.get("between_beam_tcp_delay_sec", 5)
        delay_tcp_pc   = self.config.get("between_tcp_pc_delay_sec", 15)

        # 1) PC 순차 OFF
        self.group_pc_off()

        # 2) PC → TCP 사이 대기 (ON 때의 TCP→PC 딜레이와 동일)
        time.sleep(delay_tcp_pc)

        # 3) TCP 출력 순차 OFF
        self.group_tcp_off()

        # 4) TCP → BEAM 사이 대기 (ON 때의 BEAM→TCP 딜레이와 동일)
        time.sleep(delay_beam_tcp)

        # 5) 프로젝터 순차 OFF
        self.group_beam_off()

    def group_pc_on(self):
        d = self.config.get("sequential_delay_sec",1)
        for pc in self.config.get("pcs", []):
            self.pc_on(pc["ip"]); time.sleep(d)

    def group_pc_off(self):
        d = self.config.get("sequential_delay_sec", 1)

        # ✅ 먼저 모든 PC에 대해 shutdown_pending을 미리 설정
        for pc in self.config.get("pcs", []):
            key = f"{pc['ip']}:{pc.get('port', 5050)}"
            self.pc_shutdown_pending[key] = True

        # ✅ 이후 실제 shutdown 명령 전송
        for pc in self.config.get("pcs", []):
            self.pc_off(pc["ip"])
            time.sleep(d)

        # 🔄 shutdown 후 probe로 상태 다시 확인
        threading.Thread(target=self._post_shutdown_pc_probe, daemon=True).start()

    def group_pc_reboot(self):
        d = self.config.get("sequential_delay_sec", 1)
        for pc in self.config.get("pcs", []):
            self.pc_reboot(pc["ip"])
            time.sleep(d)

    def group_beam_on(self):
        d = self.config.get("sequential_delay_sec",1)
        for b in self.config.get("projectors", []):
            self.beam_on(b["ip"], b.get("port",4352)); time.sleep(d)

    def group_beam_off(self):
        d = self.config.get("sequential_delay_sec",1)
        for b in self.config.get("projectors", []):
            self.beam_off(b["ip"], b.get("port",4352)); time.sleep(d)

    def group_shutter_open(self):
        import threading
        threads = []
        for b in self.config.get("projectors", []):
            t = threading.Thread(target=self.beam_shutter_open, args=(b["ip"], b.get("port",4352)), daemon=True)
            t.start(); threads.append(t)
        for t in threads: t.join(timeout=0.8)

    def group_shutter_close(self):
        import threading
        threads = []
        for b in self.config.get("projectors", []):
            t = threading.Thread(target=self.beam_shutter_close, args=(b["ip"], b.get("port",4352)), daemon=True)
            t.start(); threads.append(t)
        for t in threads: t.join(timeout=0.8)

    def group_tcp_on(self):
        """
        Send TCP messages for entries that are marked to run on ALL ON.
        Each send is: connect -> send -> close (no persistent connection).
        """
        delay = self.config.get("sequential_delay_sec", 1)
        for item in self.config.get("tcp_outputs", []):
            if item.get("use_on"):
                ip = item.get("ip")
                port = int(item.get("port", 0) or 0)
                data = item.get("data", "")
                if not ip or not port or not data:
                    continue
                self._tcp_send(ip, port, data.encode("utf-8", errors="ignore"))
                self.log(f"TCP ON sent -> {ip}:{port} ({data})")
                time.sleep(delay)

    def group_tcp_off(self):
        """
        Send TCP messages for entries that are marked to run on ALL OFF.
        Each send is: connect -> send -> close (no persistent connection).
        """
        delay = self.config.get("sequential_delay_sec", 1)
        for item in self.config.get("tcp_outputs", []):
            if item.get("use_off"):
                ip = item.get("ip")
                port = int(item.get("port", 0) or 0)
                data = item.get("data", "")
                if not ip or not port or not data:
                    continue
                self._tcp_send(ip, port, data.encode("utf-8", errors="ignore"))
                self.log(f"TCP OFF sent -> {ip}:{port} ({data})")
                time.sleep(delay)

    # ---- OSC OPS ----
    def _osc_build_message(self, address: str, value, vtype: str) -> bytes:
        """Build a minimal OSC packet for a single argument.

        Supports: float, int, string
        """
        def pad4(b: bytes) -> bytes:
            return b + (b"\x00" * ((4 - (len(b) % 4)) % 4))

        if not address.startswith("/"):
            address = "/" + address.lstrip("/")
        addr_bin = pad4(address.encode("utf-8") + b"\x00")  # address is null-terminated then padded

        vtype = (vtype or "float").lower()
        if vtype not in ("float", "int", "string"):
            vtype = "float"

        if vtype == "float":
            tag_char = "f"
            try:
                val = float(value)
            except Exception:
                val = 0.0
            arg = struct.pack(">f", val)
        elif vtype == "int":
            tag_char = "i"
            try:
                val = int(float(value))
            except Exception:
                val = 0
            arg = struct.pack(">i", val)
        else:
            tag_char = "s"
            sval = str(value)
            arg = pad4(sval.encode("utf-8") + b"\x00")  # string is padded separately

        # type tag string
        tag = ("," + tag_char).encode("ascii") + b"\x00"
        tag_bin = pad4(tag)

        if tag_char in ("f", "i"):
            arg_bin = pad4(arg)
        else:
            arg_bin = arg

        return addr_bin + tag_bin + arg_bin

    def _osc_send(self, ip: str, port: int, address: str, value, vtype: str):
        try:
            msg = self._osc_build_message(address, value, vtype)
        except Exception as e:
            self.log(f"OSC build failed {ip}:{port} {address} -> {e}")
            return
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(msg, (ip, int(port)))
            s.close()
            self.log(f"OSC sent {ip}:{port} {address}")
        except Exception as e:
            self.log(f"OSC send failed {ip}:{port} {address} -> {e}")

    def send_osc_index(self, idx: int, phase: str = "press"):
        """
        메인페이지 OSC 버튼용.
        phase="press"  → ON 값 전송
        phase="release"→ OFF 값 전송

        config 의 value 필드가 "1,0" 이면
        - press: 1
        - release: 0

        "0,1" 이면 반대로,
        그냥 "1" 하나만 적혀 있으면
        - press: 1
        - release: 0 으로 동작.
        """
        buttons = self.config.get("osc_buttons", [])
        if not (0 <= idx < len(buttons)):
            self.log(f"OSC index {idx} out of range")
            return

        cfg = buttons[idx]
        if not cfg.get("enabled", False):
            self.log(f"OSC {idx+1} disabled; skip.")
            return

        ip = (cfg.get("ip") or "").strip()
        port_raw = cfg.get("port", 0)
        try:
            port = int(port_raw or 0)
        except Exception:
            port = 0
        addr = (cfg.get("address") or "").strip()
        raw_val = str(cfg.get("value", "")).strip()
        vtype = (cfg.get("type") or "float").lower()

        if not ip or not port or not addr:
            self.log(f"OSC {idx+1} invalid config; skip.")
            return

        # "1,0" 형태면 앞이 press, 뒤가 release
        on_str, off_str = None, None
        if "," in raw_val:
            parts = [p.strip() for p in raw_val.split(",", 1)]
            on_str = parts[0] or "1"
            off_str = parts[1] or "0"
        else:
            # 값이 하나만 있으면 ON=value, OFF=0 으로
            on_str = raw_val or "1"
            off_str = "0"

        def cast(val_str):
            if vtype == "int":
                try:
                    return int(float(val_str))
                except Exception:
                    return 0
            if vtype == "float":
                try:
                    return float(val_str)
                except Exception:
                    return 0.0
            # string
            return val_str

        if phase == "release":
            value = cast(off_str)
            tag = "UP"
        else:
            value = cast(on_str)
            tag = "DOWN"

        self.log(f"OSC {idx+1} {tag} -> {ip}:{port} {addr} ({vtype}={value})")
        self._osc_send(ip, port, addr, value, vtype)

    # ---- PC OPS ----
    def _find_pc(self, ip):
        for pc in self.config.get("pcs", []):
            if pc.get("ip") == ip: return pc
        return None

    def pc_on(self, ip):
        pc = self._find_pc(ip)
        if not pc:
            self.log(f"PC not found: {ip}")
            return

        mac = (pc.get("mac", "") or "").replace("-", ":")
        if not mac:
            self.log(f"WOL skipped (no MAC) -> {ip}")
            return

        # wol_repeat 설정값 (기본 2회)
        repeat = self.config.get("wol_repeat", 2)
        try:
            repeat = int(repeat)
        except Exception:
            repeat = 1
        if repeat < 1:
            repeat = 1

        for i in range(repeat):
            self._wol(mac)
            # 여러 번 보낼 때는 약간 간격을 둔다 (0.5초 정도)
            if i + 1 < repeat:
                time.sleep(0.5)

        if repeat == 1:
            self.log(f"WOL sent -> {ip} ({mac})")
        else:
            self.log(f"WOL x{repeat} sent -> {ip} ({mac})")

        # PC 전원을 켜는 동안 PJLink 폴링 에러 알림이 쏟아지지 않도록
        self._set_beam_transition_for_all_beams()

    def pc_off(self, ip):
        pc = self._find_pc(ip)
        if not pc:
            self.log(f"PC not found: {ip}")
            return

        key = f"{ip}:{pc.get('port', 5050)}"
        self.pc_shutdown_pending[key] = True  # 🔒 텔레그램 알림 방지용
        self._tcp_send(ip, pc.get("port", 5050), b"shutdown")
        self.log(f"PC OFF sent -> {ip}:{pc.get('port', 5050)}")

        # PC를 순차적으로 끌 때도 네트워크 부하로 인한 BEAM 에러 알림을 완화
        self._set_beam_transition_for_all_beams()

    def pc_reboot(self, ip):
        pc = self._find_pc(ip)
        if not pc:
            self.log(f"PC not found: {ip}")
            return

        key = f"{ip}:{pc.get('port', 5050)}"
        self.pc_shutdown_pending[key] = True  # 🔒 텔레그램 알림 방지용
        self._tcp_send(ip, pc.get("port", 5050), b"reboot")
        self.log(f"PC REBOOT sent -> {ip}:{pc.get('port', 5050)}")

        # 재부팅 시에도 잠시 BEAM 에러 알림을 완화
        self._set_beam_transition_for_all_beams()

    # ---- PROJECTOR OPS ----
    def _find_beam(self, ip, port=None):
        for b in self.config.get("projectors", []):
            if b.get("ip") == ip and (port is None or int(b.get("port",4352)) == int(port)):
                return b
        return None

    def beam_on(self, ip, port=None):
        b = self._find_beam(ip, port)
        if not b:
            self.log(f"Beam not found: {ip}:{port if port else ''}")
            return

        host = b.get("ip")
        p = b.get("port", 4352)
        pw = b.get("password", "")
        key = f"{host}:{p}"

        try:
            PJLink(host, p, pw).power_on()
            self.log(f"BEAM ON -> {host}:{p}")
            # 정상 동작이면 에러 플래그 리셋
            self.beam_error_flags[key] = False
            # 예열 구간 동안 BEAM 모니터링 에러 알림을 완화하기 위한 grace window 설정
            try:
                grace = float(self.config.get("beam_transition_grace_sec", 90.0))
            except Exception:
                grace = 90.0
            self.beam_transition_until[key] = time.time() + grace
        except Exception as e:
            self.log(f"BEAM ON FAILED -> {host}:{p} -> {e}")

    def beam_off(self, ip, port=None):
        b = self._find_beam(ip, port)
        if not b:
            self.log(f"Beam not found: {ip}:{port if port else ''}")
            return

        host = b.get("ip")
        p = b.get("port", 4352)
        pw = b.get("password", "")
        key = f"{host}:{p}"

        try:
            PJLink(host, p, pw).power_off()
            self.log(f"BEAM OFF -> {host}:{p}")
            # 정상 동작이면 에러 플래그 리셋
            self.beam_error_flags[key] = False
            # 쿨다운 구간 동안 BEAM 모니터링 에러 알림을 완화하기 위한 grace window 설정
            try:
                grace = float(self.config.get("beam_transition_grace_sec", 90.0))
            except Exception:
                grace = 90.0
            self.beam_transition_until[key] = time.time() + grace
        except Exception as e:
            self.log(f"BEAM OFF FAILED -> {host}:{p} -> {e}")

    def beam_shutter_close(self, ip, port=None):
        b = self._find_beam(ip, port)
        if not b: self.log(f"Beam not found: {ip}:{port if port else ''}"); return
        PJLink(b["ip"], b.get("port",4352), b.get("password","")).shutter_close()
        self._update_beam_state(ip, port, shutter="close")

    def beam_shutter_open(self, ip, port=None):
        b = self._find_beam(ip, port)
        if not b: self.log(f"Beam not found: {ip}:{port if port else ''}"); return
        PJLink(b["ip"], b.get("port",4352), b.get("password","")).shutter_open()
        self._update_beam_state(ip, port, shutter="open")

    def _update_beam_state(self, ip, port, shutter=None, status=None):
        with self.state_lock:
            beams = self.state.get("projectors", [])
            changed = False
            for i, b in enumerate(beams):
                if b.get("ip")==ip and int(b.get("port",4352))==int(port):
                    nb = dict(b)
                    if shutter is not None: nb["shutter"] = shutter
                    if status  is not None: nb["status"]  = status
                    beams[i] = nb; changed=True
            if changed:
                self.state["projectors"] = beams

    # ---- QUICK PROBE LOGIC ----
    def _quick_pc_probe_once(self):
        """
        RemotePower.exe(기본 5050 포트)로 TCP 접속을 시도해서
        - 접속 성공  → 해당 PC 상태: "on"
        - 접속 실패  → 해당 PC 상태: "off"
        로 판단한다.
        """

        pcs = self.config.get("pcs", [])
        results = {}

        for pc in pcs:
            ip = pc.get("ip")
            port = pc.get("port", 5050)
            key = f"{ip}:{port}"
            online = False

            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.0)
                s.connect((ip, port))
                try:
                    s.sendall(b"ping\n")
                except Exception:
                    pass
                online = True
            except Exception:
                online = False
            finally:
                try:
                    s.close()
                except Exception:
                    pass

            pending = self.pc_shutdown_pending.get(key, False)
            is_first = not self.initial_probe_complete

            if online:
                # PC가 다시 켜졌으면 오류 플래그 리셋
                self.pc_error_flags[key] = False
            else:
                if pending:
                    # ✅ 우리가 방금 보낸 OFF/REBOOT/스케줄 OFF 때문에 꺼진 경우
                    self.log(f"[DEBUG] 예상된 종료 - 알림 생략")
                    # 이 OFF 상태는 '정상 종료된 상태'로 간주해서
                    # 이후 계속 OFF여도 비정상 종료로 보지 않도록 플래그 고정
                    self.pc_error_flags[key] = True
                    # 그리고 더 이상 pending 상태로 남지 않도록 해제
                    self.pc_shutdown_pending[key] = False
                elif is_first:
                    self.log(f"[DEBUG] 최초 실행 감지됨 - 알림 생략")
                    self.pc_error_flags[key] = True
                elif not self.pc_error_flags.get(key, False):
                    self.send_telegram_alert(
                        f"[PC] {ip}:{port} offline (RemotePower not responding)"
                    )
                    self.log(f"[DEBUG] ⚠️ 예기치 않은 종료 - 텔레그램 알림 발송됨")
                    self.pc_error_flags[key] = True

            results[ip] = "on" if online else "off"

        # ✅ 최초 실행 이후에는 초기 플래그 해제
        self.initial_probe_complete = True

        # 상태 업데이트
        with self.state_lock:
            prev_status = {
                pc.get("ip"): pc.get("status")
                for pc in self.state.get("pcs", [])
            }

            new_list = []
            any_changed = False

            for pc in pcs:
                ip = pc.get("ip")
                st = results.get(ip, "off")
                new_list.append({**pc, "status": st})
                if prev_status.get(ip) != st:
                    any_changed = True

            self.state["pcs"] = new_list

        if any_changed:
            try:
                summary = ", ".join(f"{ip}:{st}" for ip, st in results.items())
                self.log(f"PC monitor (RemotePower) -> {summary}")
            except Exception:
                pass

        return any(v == "on" for v in results.values())

    def _post_shutdown_pc_probe(self):
        """그룹 PC OFF / ALL OFF 이후에 실제로 모든 PC가 꺼졌는지 확인하고
        텔레그램 알림용 플래그를 정리하는 보조 스레드.
        """
        time.sleep(5)
        deadline = time.time() + 60
        while time.time() < deadline:
            any_on = self._quick_pc_probe_once()
            if not any_on:
                # 모든 PC가 꺼졌고, shutdown_pending이 유지되고 있다면 여기서만 해제
                try:
                    pcs = self.config.get("pcs", [])
                    for pc in pcs:
                        key = f"{pc.get('ip')}:{pc.get('port', 5050)}"
                        # 이후부터는 "오늘은 꺼져 있는 것이 정상" 상태로 간주
                        self.pc_shutdown_pending[key] = False
                        # 이미 정상적으로 OFF 처리된 상태이므로,
                        # 이후 OFF 모니터링에서 다시 알림을 보내지 않도록 플래그를 세팅
                        self.pc_error_flags[key] = True
                        # 🔚 이 시점부터는 더 이상 grace window가 필요 없으므로 강제로 종료
                        self.pc_expected_off_until[key] = 0.0
                    self.log("[DEBUG] 모든 PC OFF 확인됨 - shutdown_pending 초기화 + 오류플래그 셋 완료")
                    # ✅ 모든 PC OFF 후 초기화했으면, 추가 모니터링은 하지 않는다!
                    return
                except Exception:
                    self.log("[DEBUG] shutdown_pending 초기화 중 예외 발생")
                    return
            time.sleep(5)
        self.log("Post-shutdown PC probe sequence finished.")

    # ---- ALL ON 5분뒤 체크  ----
    def schedule_post_all_on_check(self, delay_sec: int = 300):
        """
        자동 스케줄 ALL ON 이후 delay_sec초 뒤에
        아직 켜지지 않은 PC/BEAM을 텔레그램으로 알려준다.
        (평상시 상시 모니터링 알림이 아니라, 스케줄 ALL ON용 1회 체크)
        """
        def _job():
            try:
                # 부팅/전원 안정화 대기
                time.sleep(delay_sec)

                # 현재 상태 스냅샷
                with self.state_lock:
                    pcs_snapshot = list(self.state.get("pcs", []))
                    beams_snapshot = list(self.state.get("projectors", []))

                # 아직 켜지지 않은 PC
                off_pcs = [pc for pc in pcs_snapshot if str(pc.get("status")) != "on"]
                # 아직 켜지지 않은 BEAM
                off_beams = [b for b in beams_snapshot if str(b.get("status")) != "on"]

                for pc in off_pcs:
                    ip = pc.get("ip", "unknown")
                    port = pc.get("port", 5050)
                    # 메시지 짧은 형식
                    self.send_telegram_alert(
                        f"[PC] {ip}:{port} offline after ALL ON (5min timeout)"
                    )

                for b in off_beams:
                    ip = b.get("ip", "unknown")
                    port = b.get("port", 4352)
                    status = b.get("status", "unknown")
                    self.send_telegram_alert(
                        f"[BEAM] {ip}:{port} not on after ALL ON "
                        f"(5min timeout, status={status})"
                    )
            except Exception as e:
                self.log(f"Post ALL ON check failed: {e}")

        threading.Thread(target=_job, daemon=True).start()

    # ---- MONITOR LOOP ----
    def _monitor_loop(self):
        base_interval = 1
        while not self._stop.is_set():
            now = time.time()
            do_pcs = (now - self._last_pc_poll) >= max(1, int(self.config.get("monitor_interval_sec", 3)))
            do_beams = (now - self._last_beam_poll) >= 3

            # --- PC 상태: RemotePower TCP로만 체크 ---
            if do_pcs:
                # RemotePower.exe(포트 5050)에 TCP 접속 시도하여 상태 갱신
                self._quick_pc_probe_once()
                self._last_pc_poll = now

            # --- BEAM 상태 모니터링 + 오류 알림 ---
            if do_beams:
                proj = self.config.get("projectors", [])
                if proj:
                    b = proj[self._beam_idx % len(proj)]
                    host = b.get("ip")
                    port = int(b.get("port", 4352))
                    key = f"{host}:{port}"
                    try:
                        pj = PJLink(host, port, b.get("password", ""))
                        pow_state = pj.get_power_state()
                        status = "on" if pow_state == "on" else ("off" if pow_state == "off" else "error")

                        # --- 셔터 상태 항상 읽기 + 값 정규화 ---
                        sh = None
                        try:
                            raw_sh = pj.get_shutter_state()
                            if raw_sh is not None:
                                s = str(raw_sh).strip().lower()
                                # Panasonic 등 AVMT=30(열림), 31(닫힘) 대응
                                if s in ("30", "open", "0"):
                                    sh = "open"
                                elif s in ("31", "close", "1"):
                                    sh = "close"
                                else:
                                    # 다른 브랜드에서 이미 "open"/"close"를 주는 경우 등을 그대로 유지
                                    sh = raw_sh
                        except Exception:
                            sh = None

                        # 상태를 state["projectors"]에 반영
                        with self.state_lock:
                            beams = self.state.get("projectors", [])
                            updated = False
                            for i, bb in enumerate(beams):
                                if bb.get("ip") == host and int(bb.get("port", 4352)) == port:
                                    nb = dict(bb)
                                    nb["name"] = b.get("name", nb.get("name", ""))
                                    nb["ip"] = host
                                    nb["port"] = port
                                    nb["status"] = status
                                    if sh is not None:
                                        nb["shutter"] = sh
                                    beams[i] = nb
                                    updated = True
                            if not updated:
                                entry = {
                                    "name": b.get("name", ""),
                                    "ip": host,
                                    "port": port,
                                    "status": status,
                                }
                                if sh is not None:
                                    entry["shutter"] = sh
                                beams.append(entry)
                                self.state["projectors"] = beams

                        # --- 여기서 모니터링 기반 BEAM 오류 알림 처리 ---
                        is_error = (status == "error")
                        if is_error:
                            # 처음 error 상태로 판정될 때만 로그 + 텔레그램 1번알림
                            if not self.beam_error_flags.get(key, False):
                                self.log(f"[BEAM] Detected failed -> {host}:{port} (status={status})")
                                self.send_telegram_alert(
                                    f"[BEAM] Detected failed -> {host}:{port} (status={status})"
                                )
                                self.beam_error_flags[key] = True
                        else:
                            # 이전에 에러였는데 지금은 정상으로 돌아온 경우
                            if self.beam_error_flags.get(key, False):
                                self.log(f"[BEAM] Back to normal -> {host}:{port} (status={status})")
                            self.beam_error_flags[key] = False

                        self._beam_idx += 1

                    except Exception as e:
                        self.log(f"[BEAM] Detected problem -> {host}:{port} -> {e}")
                        # 모니터링 자체가 실패한 경우도 처음 한 번만 알림
                        if not self.beam_error_flags.get(key, False):
                            self.send_telegram_alert(
                                f"[BEAM] Detected problem -> {host}:{port}\n{e}"
                            )
                            self.beam_error_flags[key] = True

                self._last_beam_poll = now

            time.sleep(base_interval)

    # ---- HELPERS ----
    def _wol(self, mac):
        mac = mac.replace(":", "").replace("-", "").lower()
        if len(mac) != 12: 
            self.log(f"Invalid MAC: {mac}")
            return
        data = bytes.fromhex("FF"*6 + mac*16)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(data, ("<broadcast>", 9))
        s.close()

    def _tcp_send(self, ip, port, payload: bytes):
        key = f"{ip}:{port}"

        # 이 payload가 PC shutdown/reboot 명령인지 미리 판별
        is_pc_cmd = False
        try:
            if isinstance(payload, (bytes, bytearray)):
                low = payload.lower()
                is_pc_cmd = (b"shutdown" in low) or (b"reboot" in low)
            elif isinstance(payload, str):
                low = payload.lower()
                is_pc_cmd = ("shutdown" in low) or ("reboot" in low)
        except Exception:
            is_pc_cmd = False

        # ✅ 명령 전이라도 먼저 pending 플래그를 설정 (텔레그램 알림 막기 위함)
        if is_pc_cmd:
            self.pc_shutdown_pending[key] = True
            # 명령 직후 일정 시간 동안은 "예상된 종료"로 간주하기 위한 시간 기록
            self.pc_expected_off_until[key] = time.time() + 60.0  # 60초 동안 grace

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5.0)
            s.connect((ip, port))

            time.sleep(1.0)

            # payload를 bytes로 변환하면서,
            # 이것이 PDU ON/OFF 명령인지도 같이 판별한다.
            if isinstance(payload, str):
                data = payload.encode("utf-8", errors="ignore")
                upper = payload.upper()
                is_pdu_cmd = upper.startswith("PDU ")
            else:
                data = bytes(payload)
                try:
                    upper = data.decode("ascii", errors="ignore").upper()
                except Exception:
                    upper = ""
                is_pdu_cmd = upper.startswith("PDU ")

            # ⚠ PDU 릴레이용 명령(PDU ON / PDU OFF)은
            #    친구 스케줄러와 동일하게 개행문자 없이
            #    "PDU OFF" 딱 이것만 보내야 한다.
            #
            # RemotePower, 기타 TCP 장비들은 기존처럼 \r\n 붙여서 전송.
            if (not is_pdu_cmd) and (not data.endswith(b"\n")):
                data += b"\r\n"

            s.sendall(data)
            self.log(f"TCP sent {ip}:{port} ({len(data)} bytes)")

            # 상태 초기화
            self.pc_error_flags[key] = False
            self.tcp_error_flags[key] = False

            try:
                s.shutdown(socket.SHUT_WR)
            except Exception:
                pass
            time.sleep(0.5)

        except Exception as e:
            msg = f"TCP send failed {ip}:{port} -> {e}"
            self.log(msg)

            try:
                if is_pc_cmd:
                    if not self.pc_error_flags.get(key, False):
                        self.send_telegram_alert(
                            f"[PC] TCP command failed -> {ip}:{port}\n{e}"
                        )
                        self.pc_error_flags[key] = True
                else:
                    if not self.tcp_error_flags.get(key, False):
                        self.send_telegram_alert(
                            f"[TCP BUTTON] TCP send failed -> {ip}:{port}\n{e}"
                        )
                        self.tcp_error_flags[key] = True
            except Exception:
                pass

        finally:
            try:
                s.close()
            except Exception:
                pass
