import socket, hashlib
CR = "\r"

class PJLink:
    def __init__(self, host, port=4352, password=""):
        self.host = host
        self.port = int(port) if port else 4352
        self.password = password or ""

    def _connect(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect((self.host, self.port))
        banner = s.recv(1024).decode("ascii", errors="ignore")
        auth = None
        if banner.startswith("PJLINK 1"):
            rnd = banner.strip().split()[-1]
            auth = hashlib.md5((rnd + self.password).encode("ascii")).hexdigest()
        return s, auth

    def _exchange(self, payload: str) -> str:
        s, auth = self._connect()
        try:
            cmd = payload if payload.endswith(CR) else payload + CR
            to_send = (auth + cmd) if auth else cmd
            s.sendall(to_send.encode("ascii", errors="ignore"))
            s.settimeout(3.0)
            data = s.recv(1024).decode("ascii", errors="ignore")
            return data
        finally:
            try: s.close()
            except: pass

    def power_on(self): self._exchange("%1POWR 1")
    def power_off(self): self._exchange("%1POWR 0")

    def get_power_state(self):
        try:
            resp = self._exchange("%1POWR ?")
            if "=" in resp:
                code = resp.split("=",1)[1].strip()
                if code.startswith("1"): return "on"
                if code.startswith("0"): return "off"
                return "transition"
        except Exception:
            pass
        return "error"

    def shutter_close(self): self._exchange("%1AVMT 30")
    def shutter_open(self):  self._exchange("%1AVMT 31")

    def get_shutter_state(self):
        try:
            resp = self._exchange("%1AVMT ?")
            if "=" in resp:
                code = resp.split("=",1)[1].strip()
                if code.startswith("31"): return "open"
                if code.startswith("30"): return "close"
        except Exception:
            pass
        return "unknown"
