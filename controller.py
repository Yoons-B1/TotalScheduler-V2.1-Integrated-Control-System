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
        self.initial_probe_complete = False

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
        try:
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
                return  

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
            requests.post(url, data=data, timeout=5)
        except Exception as e:
            self.log(f"Telegram alert failed: {e}")

    def __init__(self, app_name: str, author: str):
        self.app_name = app_name
        self.author = author
        self.base_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
        self.config_dir = os.path.join(self.base_dir, ".config")
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_path = os.path.join(self.config_dir, "config.json")

        self.log_dir = os.path.join(self.config_dir, "logs")
        os.makedirs(self.log_dir, exist_ok=True)

        self.beam_error_flags = {}
        self.pc_error_flags = {}
        self.tcp_error_flags = {}

        self.beam_transition_until = {}

        self.pc_shutdown_pending = {}

        self.pc_expected_off_until = {}

        self.initial_probe_complete = False

        self._last_telegram_text = None
        self._last_telegram_time = 0.0

        existed = os.path.exists(self.config_path)

        self.config = self._load_or_create_default()

        if "web_port" not in self.config:
            self.config["web_port"] = 9999

        self.web_server_ok = False


        self.first_run = not existed

        if "tcp_outputs" not in self.config:
            self.config["tcp_outputs"] = []

        if "osc_buttons" not in self.config:
            self.config["osc_buttons"] = []

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
        self._log_ring = []  

        self._op_lock = threading.Lock()
        self._op_running = False
        self._op_name = ""

        self._keepers = {}

        self._last_pc_poll = 0.0
        self._last_beam_poll = 0.0
        self._beam_idx = 0

        self._need_shutter_probe = set()

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
        self._log_queue.put(line)
        try:
            self._log_ring.append(line)
            if len(self._log_ring) > 500:
                self._log_ring = self._log_ring[-500:]
        except Exception:
            self._log_ring = [line]

        if msg.startswith("[DEBUG]") or msg.startswith("DEBUG:"):
            return

        try:
            date_str = _t.strftime("%Y-%m-%d")
            filename = f"TotalScheduler_{date_str}.log"
            path = os.path.join(self.log_dir, filename)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

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
                pass
        except Exception:
            pass

    def _log_dispatch_loop(self):
        while not self._stop.is_set():
            try: line = self._log_queue.get(timeout=0.5)
            except queue.Empty: continue
            for fn in list(self._log_listeners):
                try: fn(line)
                except Exception: pass

    def get_recent_logs(self, limit: int = 100):
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
                    "wol_repeat": 2,   
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
        return

    def _set_beam_transition_for_all_beams(self, grace_sec: float = None):
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

    def all_on(self):

        delay_beam_tcp = self.config.get("between_beam_tcp_delay_sec", 5)
        delay_tcp_pc   = self.config.get("between_tcp_pc_delay_sec", 15)

        self.group_beam_on()

        time.sleep(delay_beam_tcp)

        self.group_tcp_on()

        time.sleep(delay_tcp_pc)

        self.group_pc_on()

    def all_off(self):

        delay_beam_tcp = self.config.get("between_beam_tcp_delay_sec", 5)
        delay_tcp_pc   = self.config.get("between_tcp_pc_delay_sec", 15)

        self.group_pc_off()

        time.sleep(delay_tcp_pc)

        self.group_tcp_off()

        time.sleep(delay_beam_tcp)

        self.group_beam_off()

    def group_pc_on(self):
        d = self.config.get("sequential_delay_sec",1)
        for pc in self.config.get("pcs", []):
            self.pc_on(pc["ip"]); time.sleep(d)

    def group_pc_off(self):
        d = self.config.get("sequential_delay_sec", 1)

        for pc in self.config.get("pcs", []):
            key = f"{pc['ip']}:{pc.get('port', 5050)}"
            self.pc_shutdown_pending[key] = True

        for pc in self.config.get("pcs", []):
            self.pc_off(pc["ip"])
            time.sleep(d)

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

    def _osc_build_message(self, address: str, value, vtype: str) -> bytes:
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

        on_str, off_str = None, None
        if "," in raw_val:
            parts = [p.strip() for p in raw_val.split(",", 1)]
            on_str = parts[0] or "1"
            off_str = parts[1] or "0"
        else:
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

        repeat = self.config.get("wol_repeat", 2)
        try:
            repeat = int(repeat)
        except Exception:
            repeat = 1
        if repeat < 1:
            repeat = 1

        for i in range(repeat):
            self._wol(mac)
            if i + 1 < repeat:
                time.sleep(0.5)

        if repeat == 1:
            self.log(f"WOL sent -> {ip} ({mac})")
        else:
            self.log(f"WOL x{repeat} sent -> {ip} ({mac})")

        self._set_beam_transition_for_all_beams()

    def pc_off(self, ip):
        pc = self._find_pc(ip)
        if not pc:
            self.log(f"PC not found: {ip}")
            return

        key = f"{ip}:{pc.get('port', 5050)}"
        self.pc_shutdown_pending[key] = True  
        self._tcp_send(ip, pc.get("port", 5050), b"shutdown")
        self.log(f"PC OFF sent -> {ip}:{pc.get('port', 5050)}")

        self._set_beam_transition_for_all_beams()

    def pc_reboot(self, ip):
        pc = self._find_pc(ip)
        if not pc:
            self.log(f"PC not found: {ip}")
            return

        key = f"{ip}:{pc.get('port', 5050)}"
        self.pc_shutdown_pending[key] = True
        self._tcp_send(ip, pc.get("port", 5050), b"reboot")
        self.log(f"PC REBOOT sent -> {ip}:{pc.get('port', 5050)}")

        self._set_beam_transition_for_all_beams()

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
            self.beam_error_flags[key] = False
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
            self.beam_error_flags[key] = False
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

    def _quick_pc_probe_once(self):

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
                self.pc_error_flags[key] = False
            else:
                if pending:
                    self.log(f"[DEBUG] 예상된 종료 - 알림 생략")
                    self.pc_error_flags[key] = True
                    self.pc_shutdown_pending[key] = False
                elif is_first:
                    self.log(f"[DEBUG] 최초 실행 감지됨 - 알림 생략")
                    self.pc_error_flags[key] = True
                elif not self.pc_error_flags.get(key, False):
                    self.send_telegram_alert(
                        f"[PC] {ip}:{port} offline (RemotePower not responding)"
                    )
                    self.log(f"[DEBUG] 예기치 않은 종료")
                    self.pc_error_flags[key] = True

            results[ip] = "on" if online else "off"

        self.initial_probe_complete = True

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
        time.sleep(5)
        deadline = time.time() + 60
        while time.time() < deadline:
            any_on = self._quick_pc_probe_once()
            if not any_on:
                try:
                    pcs = self.config.get("pcs", [])
                    for pc in pcs:
                        key = f"{pc.get('ip')}:{pc.get('port', 5050)}"
                        self.pc_shutdown_pending[key] = False
                        self.pc_error_flags[key] = True
                        self.pc_expected_off_until[key] = 0.0
                    self.log("[DEBUG] 모든 PC OFF 확인됨 - shutdown_pending 초기화 + 오류플래그 셋 완료")
                    return
                except Exception:
                    self.log("[DEBUG] shutdown_pending 초기화 중 예외 발생")
                    return
            time.sleep(5)
        self.log("Post-shutdown PC probe sequence finished.")

    def schedule_post_all_on_check(self, delay_sec: int = 300):
        def _job():
            try:
                time.sleep(delay_sec)

                with self.state_lock:
                    pcs_snapshot = list(self.state.get("pcs", []))
                    beams_snapshot = list(self.state.get("projectors", []))

                off_pcs = [pc for pc in pcs_snapshot if str(pc.get("status")) != "on"]
                off_beams = [b for b in beams_snapshot if str(b.get("status")) != "on"]

                for pc in off_pcs:
                    ip = pc.get("ip", "unknown")
                    port = pc.get("port", 5050)
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

    def _monitor_loop(self):
        base_interval = 1
        while not self._stop.is_set():
            now = time.time()
            do_pcs = (now - self._last_pc_poll) >= max(1, int(self.config.get("monitor_interval_sec", 3)))
            do_beams = (now - self._last_beam_poll) >= 3

            if do_pcs:
                self._quick_pc_probe_once()
                self._last_pc_poll = now

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

                        sh = None
                        try:
                            raw_sh = pj.get_shutter_state()
                            if raw_sh is not None:
                                s = str(raw_sh).strip().lower()
                                if s in ("30", "open", "0"):
                                    sh = "open"
                                elif s in ("31", "close", "1"):
                                    sh = "close"
                                else:
                                    sh = raw_sh
                        except Exception:
                            sh = None

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

                        is_error = (status == "error")
                        if is_error:
                            if not self.beam_error_flags.get(key, False):
                                self.log(f"[BEAM] Detected failed -> {host}:{port} (status={status})")
                                self.send_telegram_alert(
                                    f"[BEAM] Detected failed -> {host}:{port} (status={status})"
                                )
                                self.beam_error_flags[key] = True
                        else:
                            if self.beam_error_flags.get(key, False):
                                self.log(f"[BEAM] Back to normal -> {host}:{port} (status={status})")
                            self.beam_error_flags[key] = False

                        self._beam_idx += 1

                    except Exception as e:
                        self.log(f"[BEAM] Detected problem -> {host}:{port} -> {e}")
                        if not self.beam_error_flags.get(key, False):
                            self.send_telegram_alert(
                                f"[BEAM] Detected problem -> {host}:{port}\n{e}"
                            )
                            self.beam_error_flags[key] = True

                self._last_beam_poll = now

            time.sleep(base_interval)

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

        if is_pc_cmd:
            self.pc_shutdown_pending[key] = True
            self.pc_expected_off_until[key] = time.time() + 60.0  

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5.0)
            s.connect((ip, port))

            time.sleep(1.0)

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

            if (not is_pdu_cmd) and (not data.endswith(b"\n")):
                data += b"\r\n"

            s.sendall(data)
            self.log(f"TCP sent {ip}:{port} ({len(data)} bytes)")

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
