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

        # ALL ON / ALL OFF 사이 딜레이 기본값
        if "between_beam_tcp_delay_sec" not in self.config:
            self.config["between_beam_tcp_delay_sec"] = 5   # BEAM → TCP
        if "between_tcp_pc_delay_sec" not in self.config:
            self.config["between_tcp_pc_delay_sec"] = 15  # TCP → PC

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

        # contact_message / web_group_title 기본값 먼저 세팅
        self.contact_message = self.config.get(
            "contact_message",
            "CONTACT : CreDL MEDIA - Yoons.B1",
        )

        self.web_group_title = self.config.get(
            "web_group_title",
            "Group Control",
        )

        # --- V1.5 → V1.6 호환: state_port 자동 추가 ---
        changed = False
        for pc in self.config.get("pcs", []):
            if "state_port" not in pc:
                try:
                    base_port = int(pc.get("port", 5050))
                except Exception:
                    base_port = 5050
                # 기본 전략: 명령 포트보다 +1 포트를 상태 포트로 사용 (예: 5050 → 5051)
                pc["state_port"] = base_port + 1
                changed = True

        if changed:
            self.save_config()
            self.log("[INFO] V1.5 config를 V1.6 형식으로 자동 변환 (state_port 추가)")

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
    # ------------------------------
    #  전체 장비 상태 확인 헬퍼 함수들
    # ------------------------------
    def _get_beam_pc_status_maps(self):
        """
        state 스냅샷을 기반으로
        - PC: ip -> status
        - BEAM: (ip, port) -> status
        두 개의 dict로 정리해서 돌려준다.
        """
        snap = self.get_state_snapshot()
        pcs   = snap.get("pcs", [])
        beams = snap.get("projectors", [])

        pc_status = {pc.get("ip"): pc.get("status") for pc in pcs}
        beam_status = {
            (b.get("ip"), int(b.get("port", 4352))): b.get("status")
            for b in beams
        }
        return pc_status, beam_status

    def is_everything_on(self):
        """
        스케줄 기준 대상(모든 BEAM + 모든 PC)이
        '전부 ON 상태'일 때만 True.

        상태 정보가 없는 장비가 하나라도 있으면
        안전하게 False를 리턴해서 스케줄을 실행하도록 둔다.
        """
        pc_status, beam_status = self._get_beam_pc_status_maps()
        cfg_pcs   = self.config.get("pcs", [])
        cfg_beams = self.config.get("projectors", [])

        if not cfg_pcs and not cfg_beams:
            return False

        for pc in cfg_pcs:
            ip = pc.get("ip")
            st = pc_status.get(ip)
            if st != "on":
                return False

        for b in cfg_beams:
            ip   = b.get("ip")
            port = int(b.get("port", 4352))
            st = beam_status.get((ip, port))
            if st != "on":
                return False

        return True

    def is_everything_off(self):
        """
        스케줄 기준 대상(모든 BEAM + 모든 PC)이
        '전부 OFF 상태'일 때만 True.
        """
        pc_status, beam_status = self._get_beam_pc_status_maps()
        cfg_pcs   = self.config.get("pcs", [])
        cfg_beams = self.config.get("projectors", [])

        if not cfg_pcs and not cfg_beams:
            return False

        for pc in cfg_pcs:
            ip = pc.get("ip")
            st = pc_status.get(ip)
            if st is None or st == "on":
                return False

        for b in cfg_beams:
            ip   = b.get("ip")
            port = int(b.get("port", 4352))
            st = beam_status.get((ip, port))
            if st is None or st == "on":
                return False

        return True

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
            ip = pc.get("ip")
            port = pc.get("port", 5050)  # 명령 포트 (RemotePowerService)
            key = self._pc_key(ip, port)
            self.pc_shutdown_pending[key] = True

        # ✅ 이후 실제 shutdown 명령 전송
        for pc in self.config.get("pcs", []):
            self.pc_off(pc.get("ip"))
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
            if pc.get("ip") == ip:
                return pc
        return None

    def _pc_key(self, ip, port=None):
        """
        PC 관련 상태 딕셔너리에서 공통으로 쓰는 key.

        - 한 PC에 RemotePowerService(명령 포트)와 RemoteState(상태 포트)를
          분리해서 쓸 수 있도록, 내부 key는 항상 "ip:state_port" 형식으로 통일한다.
        """
        pcs = self.config.get("pcs", [])
        for pc in pcs:
            if pc.get("ip") != ip:
                continue

            cmd_port = int(pc.get("port", 5050))
            state_port = int(pc.get("state_port", cmd_port))

            # port가 None 이면 ip만 맞는 첫 PC,
            # port가 있으면 cmd_port나 state_port 둘 중 하나라도 맞으면 같은 PC로 본다.
            if port is None or int(port) in (cmd_port, state_port):
                return f"{ip}:{state_port}"

        # 해당 PC를 못 찾으면 그냥 받은 포트 그대로 사용 (PDU 등 다른 장비용)
        if port is None:
            port = 0
        return f"{ip}:{port}"

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

        cmd_port = pc.get("port", 5050)  # RemotePowerService 명령 포트
        key = self._pc_key(ip, cmd_port)
        self.pc_shutdown_pending[key] = True  # 🔒 텔레그램 알림 방지용

        self._tcp_send(ip, cmd_port, b"shutdown")
        self.log(f"PC OFF sent -> {ip}:{cmd_port}")

        # PC를 순차적으로 끌 때도 네트워크 부하로 인한 BEAM 에러 알림을 완화
        self._set_beam_transition_for_all_beams()

    def pc_reboot(self, ip):
        pc = self._find_pc(ip)
        if not pc:
            self.log(f"PC not found: {ip}")
            return

        cmd_port = pc.get("port", 5050)  # RemotePowerService 명령 포트
        key = self._pc_key(ip, cmd_port)
        self.pc_shutdown_pending[key] = True  # 🔒 텔레그램 알림 방지용

        self._tcp_send(ip, cmd_port, b"reboot")
        self.log(f"PC REBOOT sent -> {ip}:{cmd_port}")

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
        """
        UI에서 'Shutter CLOSE'를 눌렀을 때 실제 빔 셔터가 닫히도록 맞춘다.
        (일부 PJLink 구현에서 shutter_open/shutter_close 이름이 실제 동작과 반대로 되어 있어서,
         여기서 호출을 뒤집어서 사용한다.)
        """
        b = self._find_beam(ip, port)
        if not b:
            self.log(f"Beam not found: {ip}:{port if port else ''}")
            return

        # 실제로는 shutter_open() 이 '화면 가리기(셔터 닫힘)' 동작이라서 여기서 사용
        PJLink(b["ip"], b.get("port", 4352), b.get("password", "")).shutter_open()
        self._update_beam_state(ip, port, shutter="close")

    def beam_shutter_open(self, ip, port=None):
        """
        UI에서 'Shutter OPEN'을 눌렀을 때 실제 빔 셔터가 열리도록 맞춘다.
        """
        b = self._find_beam(ip, port)
        if not b:
            self.log(f"Beam not found: {ip}:{port if port else ''}")
            return

        # 실제로는 shutter_close() 가 '화면 표시(셔터 열림)' 동작이라서 여기서 사용
        PJLink(b["ip"], b.get("port", 4352), b.get("password", "")).shutter_close()
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
        RemotePower(RemoteState)로 TCP 접속을 시도해서
        - 접속 성공  → 해당 PC 상태: "on"
        - 접속 실패  → 해당 PC 상태: "off"
        로 판단한다.

        ※ 각 PC의 config["state_port"]가 있으면 그 포트를 기준으로 모니터링한다.
           (없으면 기존처럼 port(5050) 기준)
        """

        pcs = self.config.get("pcs", [])
        results = {}

        for pc in pcs:
            ip = pc.get("ip")
            if not ip:
                continue

            # 명령 포트 / 상태 모니터 포트
            cmd_port = int(pc.get("port", 5050))
            state_port = int(pc.get("state_port", cmd_port))

            # ✅ 항상 "ip:state_port" 기준으로 key를 통일
            key = self._pc_key(ip, state_port)
            online = False

            s = None
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.0)
                s.connect((ip, state_port))
                try:
                    s.sendall(b"ping\n")
                except Exception:
                    pass
                online = True
            except Exception:
                online = False
            finally:
                if s is not None:
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
                    self.log("[DEBUG] 예상된 종료 - 알림 생략")
                    # 이 OFF 상태는 '정상 종료된 상태'로 간주해서
                    # 이후 계속 OFF여도 비정상 종료로 보지 않도록 플래그 고정
                    self.pc_error_flags[key] = True
                    # 더 이상 pending 상태로 남지 않도록 해제
                    self.pc_shutdown_pending[key] = False
                elif is_first:
                    # 프로그램 처음 켜졌을 때 이미 꺼져 있던 PC → 알림 보내지 않음
                    self.log("[DEBUG] 최초 실행 감지됨 - 알림 생략")
                    self.pc_error_flags[key] = True
                elif not self.pc_error_flags.get(key, False):
                    # 🔴 여기서만 "예기치 않은 종료" 텔레그램 알림을 보냄
                    #   - 최초 실행 아님
                    #   - 우리가 명령(pending) 보낸 것도 아님
                    #   - 이전에는 정상(on)이었다가 지금 처음으로 off가 된 경우
                    self.send_telegram_alert(
                        f"[PC] {ip}:{state_port} offline (RemotePower not responding)"
                    )
                    self.log("[DEBUG] ⚠️ 예기치 않은 종료 - 텔레그램 알림 발송됨")
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

        # 하나라도 켜져 있는 PC가 있는지 반환
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
                        ip = pc.get("ip")
                        port = pc.get("port", 5050)
                        key = self._pc_key(ip, port)
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

    # ---- ALL ON 후 PC 자동 Reboot ----
    def schedule_pc_reboot_after_all_on(self, delay_sec: int = 300):
        """
        자동 스케줄 ALL ON 이후 delay_sec초 뒤에
        등록된 PC들을 순차적으로 reboot한다.
        UI의 'Reboot PCs after ALL ON' 옵션에서 사용.
        """
        def _job():
            try:
                # 부팅/로그온 안정화 대기
                time.sleep(delay_sec)

                pcs = self.config.get("pcs", [])
                seq_delay = float(self.config.get("sequential_delay_sec", 1))

                for pc in pcs:
                    ip = pc.get("ip")
                    port = int(pc.get("port", 5050))
                    if not ip:
                        continue

                    self.log(f"[AUTO] Reboot after ALL ON -> {ip}:{port}")
                    # 새 RemotePowerService에 'reboot' 명령 전송
                    self.tcp_send_to_pc(ip, port, "reboot")
                    time.sleep(seq_delay)

            except Exception as e:
                self.log(f"Reboot-after-ALL-ON failed: {e}")

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

                        # --- 파워 상태 읽기 ---
                        pow_state = pj.get_power_state()
                        ps = str(pow_state).strip().lower()

                        # 1) PJLink 원 상태를 raw_status로 분리
                        if ps in ("on", "1"):
                            raw_status = "on"
                        elif ps in ("off", "0", "standby"):
                            raw_status = "off"
                        else:
                            # "warm-up", "cooling" 등은 여기서 모두 error로 분류 (아래 그레이스에서 보정)
                            raw_status = "error"

                        # 2) 그레이스 윈도우 / 워밍업·쿨다운 구간 판단
                        now_ts = time.time()
                        deadline = self.beam_transition_until.get(key, 0) or 0
                        in_grace = (deadline > 0 and now_ts < deadline)

                        # UI에 보여줄 status:
                        #  - 평소에는 raw_status 그대로
                        #  - 그레이스 구간(in_grace)에서는 error라도 off로 취급해서 "빨간점"이 아니라 회색점으로 보이게
                        if raw_status == "error" and in_grace:
                            status = "off"
                        else:
                            status = raw_status

                        # --- 셔터 상태 읽기 + 정규화 (실제 동작 반대로 들어오는 경우 수정) ---
                        sh = None
                        try:
                            raw_sh = pj.get_shutter_state()
                            if raw_sh is not None:
                                s = str(raw_sh).strip().lower()

                                # ⚠ 현재 장비에서는 실제 동작이 반대로 들어오므로 다음과 같이 뒤집어서 처리:
                                #  - 실제 셔터 "닫힘" 상태는 30 / open / 0 으로 들어옴  → close 로 표시
                                #  - 실제 셔터 "열림" 상태는 31 / close / 1 으로 들어옴 → open 으로 표시
                                if s in ("30", "open", "0"):
                                    sh = "close"   # 실제 빔은 닫혀있는 상태
                                elif s in ("31", "close", "1"):
                                    sh = "open"    # 실제 빔은 열려있는 상태
                                else:
                                    # 예상 못한 문자열은 그대로 표시
                                    sh = raw_sh
                        except Exception:
                            sh = None

                        # --- state["projectors"] 업데이트 + 전원 ON 시 기본 셔터 OPEN 가정 ---
                        with self.state_lock:
                            beams = self.state.get("projectors", [])
                            updated = False
                            for i, bb in enumerate(beams):
                                if bb.get("ip") == host and int(bb.get("port", 4352)) == port:
                                    nb = dict(bb)
                                    nb["name"] = b.get("name", nb.get("name", ""))
                                    nb["ip"] = host
                                    nb["port"] = port

                                    prev_status = bb.get("status")
                                    prev_shutter = bb.get("shutter")

                                    # 셔터 최종값 결정
                                    eff_sh = sh
                                    if eff_sh is None:
                                        if prev_status != "on" and status == "on":
                                            # 🔹 OFF → ON 으로 막 켜졌는데 셔터값을 못 읽으면 기본 OPEN 가정
                                            eff_sh = "open"
                                        else:
                                            eff_sh = prev_shutter

                                    nb["status"] = status
                                    if eff_sh is not None:
                                        nb["shutter"] = eff_sh
                                    beams[i] = nb
                                    updated = True

                            if not updated:
                                # 처음 등록되는 프로젝터
                                entry = {
                                    "name": b.get("name", ""),
                                    "ip": host,
                                    "port": port,
                                    "status": status,
                                }
                                eff_sh = sh
                                if eff_sh is None and status == "on":
                                    # 🔹 처음부터 ON 상태로 잡힌 경우에도 셔터 기본 OPEN 가정
                                    eff_sh = "open"
                                if eff_sh is not None:
                                    entry["shutter"] = eff_sh
                                beams.append(entry)
                                self.state["projectors"] = beams

                        # --- BEAM 에러 플래그 & 텔레그램 알림 ---
                        #   raw_status 기준으로 "진짜 에러"인지 판단
                        is_error = (raw_status == "error") and not in_grace

                        if is_error:
                            # 처음 error 상태로 판정될 때만 로그 + 텔레그램 1번 알림
                            if not self.beam_error_flags.get(key, False):
                                self.log(f"[BEAM] Detected failed -> {host}:{port} (status={raw_status})")
                                self.send_telegram_alert(
                                    f"[BEAM] Detected failed -> {host}:{port} (status={raw_status})"
                                )
                                self.beam_error_flags[key] = True
                        else:
                            # 이전에 에러였는데 지금은 정상/쿨다운/워밍업이 끝난 상태로 돌아온 경우
                            if self.beam_error_flags.get(key, False) and not in_grace:
                                self.log(f"[BEAM] Back to normal -> {host}:{port} (status={raw_status})")
                            # 그레이스 안에서는 굳이 플래그를 건드리지 않아도 되고,
                            # 정상으로 확실히 돌아왔을 때만 False로 리셋
                            if not in_grace:
                                self.beam_error_flags[key] = False

                        self._beam_idx += 1

                    except Exception as e:
                        self.log(f"[BEAM] Detected problem -> {host}:{port} -> {e}")
                        # 모니터링 자체가 실패한 경우도, 그레이스 윈도우 안에서는 텔레그램 알림 생략
                        deadline = self.beam_transition_until.get(key, 0) or 0
                        in_grace = (deadline > 0 and time.time() < deadline)
                        if not in_grace and not self.beam_error_flags.get(key, False):
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
        # PC 명령인 경우에는 항상 "ip:state_port" 기준으로 key를 통일해서 사용
        key = self._pc_key(ip, port)

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
