import json
import threading
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# WebUI 포트
DEFAULT_WEB_PORT = 9999


def make_handler(controller):
    """
    Create a HTTP handler class bound to a specific Controller instance.
    """

    class WebUIHandler(BaseHTTPRequestHandler):
        ctrl = controller

        # ------------- low-level helpers -------------

        def _send_bytes(self, data: bytes, status: int = 200, content_type: str = "text/html; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(data)

        def _send_text(self, body: str, status: int = 200, content_type: str = "text/html; charset=utf-8"):
            if isinstance(body, str):
                data = body.encode("utf-8")
            else:
                data = body
            self._send_bytes(data, status=status, content_type=content_type)

        def _send_json(self, obj, status: int = 200):
            data = json.dumps(obj).encode("utf-8")
            self._send_bytes(data, status=status, content_type="application/json; charset=utf-8")

        def _read_json(self):
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return {}

        # ------------- HTML templates -------------

        def _remote_page_html(self) -> str:
            """
            Main remote page (status + ALL ON/OFF).
            """
            return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TotalScheduler Remote</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<meta name="apple-mobile-web-app-title" content="TotalScheduler">
<style>
body {
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background-color: #111315;
  color: #f5f5f5;
}
.app {
  max-width: 480px;
  margin: 0 auto;
  padding: 10px 12px 20px 12px;
}
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: #a0a7b3;
  margin-bottom: 6px;
}
.top-btn {
  padding: 4px 2px;
  border: none;
  background: none;
  color: #5fa8ff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
}
.top-btn:active {
  transform: scale(0.97);
  color: #ffffff;
}
.offline-banner {
  background: #7a1f2b;
  color: #ffd4d4;
  font-size: 13px;
  padding: 10px 10px;   /* 세로 길게 */
  border-radius: 10px;
  margin-bottom: 10px;
  text-align: center;
  font-weight: 600;
}
.section-title {
  font-size: 14px;
  margin: 10px 0 4px 2px;
  color: #c7ced8;
}
.btn-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}
.btn {
  flex: 1;
  padding: 12px 10px;
  border-radius: 10px;
  border: none;
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
}
.btn-on {
  background: #3fb983;
  color: #071017;
}
.btn-off {
  background: #e45858;
  color: #fff;
}
.btn:active {
  transform: scale(0.97);
  background: #f5f5f5;
  color: #111315;
}
/* 버튼이 눌렸을 때 JS가 적용하는 '흰색 번쩍' 효과 */
.btn.flash,
.small-btn.flash {
  background: #f5f5f5 !important;
  color: #111315 !important;
}
.status-card {
  background: #181c22;
  border-radius: 12px;
  padding: 10px 8px 4px 8px;
  margin-top: 8px;
}
.device-row {
  display: flex;
  align-items: center;
  padding: 6px 4px;
}
.device-row + .device-row {
  border-top: 1px solid #20252d;
}
.dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  margin-right: 8px;
}
.dot.on {
  background: #6dc36d;
}
.dot.off {
  background: #a9b2ba;
}
.dot.error {
  background: #e45858;
}
.device-main {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.device-name {
  font-size: 14px;
}
.device-ip {
  font-size: 11px;
  color: #8b95a3;
}
.device-extra {
  font-size: 11px;
  color: #c0cad5;
}
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.75);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 999;
}
.overlay-inner {
  background: #181c22;
  padding: 18px 24px;
  border-radius: 12px;
  text-align: center;
  box-shadow: 0 8px 24px rgba(0,0,0,0.6);
}
.overlay-title {
  font-size: 14px;
  color: #a0a7b3;
  margin-bottom: 6px;
}
.overlay-main {
  font-size: 18px;
  font-weight: 600;
}
</style>
</head>
<body>
<div class="overlay" id="overlay">
  <div class="overlay-inner">
    <div class="overlay-title">Running...</div>
    <div class="overlay-main" id="overlayText">ALL ON</div>
  </div>
</div>
<div class="app">
  <div class="top-bar">
    <span id="nowText">--:--:--</span>
    <button class="top-btn" onclick="location.href='/admin'">ADMIN</button>
  </div>
  <div id="offlineBanner" class="offline-banner" style="display:none;">
    Disconnected from TotalScheduler server.
  </div>

  <div class="section-title" id="groupTitle">Group Control</div>
  <div class="btn-row">
    <button class="btn btn-on" onclick="flashAndSend(this,'all_on')">ALL ON</button>
    <button class="btn btn-off" onclick="flashAndSend(this,'all_off')">ALL OFF</button>
  </div>

  <div class="status-card" id="pcCard">
    <div class="section-title">PC Status</div>
    <div id="pcList"></div>
  </div>

  <div class="status-card" id="beamCard">
    <div class="section-title">Projector Status</div>
    <div id="beamList"></div>
  </div>
</div>
<script>
const offlineBanner = document.getElementById("offlineBanner");

function flashButton(btn) {
  if (!btn) return;
  btn.classList.add("flash");
  setTimeout(() => btn.classList.remove("flash"), 120);
}

function flashAndSend(btn, action, payload) {
  flashButton(btn);
  sendAction(action, payload);
}

async function sendAction(action, payload) {
  try {
    await fetch("/api/action", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(Object.assign({action: action}, payload || {}))
    });
  } catch (e) {
    console.log("action error", e);
  }
}

function makeDeviceRow(parent, item, isBeam) {
  const row = document.createElement("div");
  row.className = "device-row";

  const dot = document.createElement("div");
  dot.className = "dot " + (item.status || "off");
  row.appendChild(dot);

  const main = document.createElement("div");
  main.className = "device-main";

  const name = document.createElement("div");
  name.className = "device-name";
  name.textContent = item.name || (isBeam ? "Projector" : "PC");

  const ip = document.createElement("div");
  ip.className = "device-ip";
  if (isBeam) {
    ip.textContent = item.ip + ":" + (item.port || 4352);
  } else {
    ip.textContent = item.ip || "";
  }

  main.appendChild(name);
  main.appendChild(ip);

  if (isBeam) {
    const extra = document.createElement("div");
    extra.className = "device-extra";
    if (item.shutter) {
      extra.textContent = "Shutter: " + item.shutter.toUpperCase();
    } else {
      extra.textContent = "";
    }
    main.appendChild(extra);
  }

  row.appendChild(main);
  parent.appendChild(row);
}

function updateState(data) {
  document.getElementById("nowText").textContent = data.now || "";

  // NEW: Group Control 제목 동적 변경
  const groupTitleEl = document.getElementById("groupTitle");
  if (groupTitleEl && data.web_group_title) {
    groupTitleEl.textContent = data.web_group_title;
  }
  
  const ov = document.getElementById("overlay");
  const txt = document.getElementById("overlayText");
  if (data.busy) {
    ov.style.display = "flex";
    txt.textContent = data.busy_name || "Running";
  } else {
    ov.style.display = "none";
  }

  const pcList = document.getElementById("pcList");
  pcList.innerHTML = "";
  (data.pcs || []).forEach(function(pc) {
    makeDeviceRow(pcList, pc, false);
  });

  const beamList = document.getElementById("beamList");
  beamList.innerHTML = "";
  (data.projectors || []).forEach(function(b) {
    makeDeviceRow(beamList, b, true);
  });
}

async function poll() {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 4000);
    const res = await fetch("/api/state", {signal: controller.signal});
    clearTimeout(timer);

    if (!res.ok) throw new Error("http " + res.status);
    const data = await res.json();
    offlineBanner.style.display = "none";
    updateState(data);
  } catch (e) {
    console.log("poll error", e);
    offlineBanner.style.display = "block";
  } finally {
    setTimeout(poll, 1000);
  }
}
poll();
</script>
</body>
</html>
"""

        def _admin_page_html(self) -> str:
            """
            Admin page (group control + per-device control + schedule + logs).
            단순하고 안정적인 버전.
            """
            return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TotalScheduler Admin</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<meta name="apple-mobile-web-app-title" content="TotalScheduler">
<style>
body {
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background-color: #111315;
  color: #f5f5f5;
}
.app {
  max-width: 520px;
  margin: 0 auto;
  padding: 10px 12px 20px 12px;
}
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: #a0a7b3;
  margin-bottom: 6px;
}
.top-btn {
  padding: 4px 2px;
  border: none;
  background: none;
  color: #5fa8ff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
}
.top-btn:active {
  transform: scale(0.97);
  color: #ffffff;
}
.offline-banner {
  background: #7a1f2b;
  color: #ffd4d4;
  font-size: 13px;
  padding: 10px 10px;
  border-radius: 10px;
  margin-bottom: 10px;
  text-align: center;
  font-weight: 600;
}
.section {
  background: #181c22;
  border-radius: 12px;
  padding: 10px 10px 8px 10px;
  margin-top: 8px;
}
.section-title {
  font-size: 14px;
  margin-bottom: 6px;
  color: #c7ced8;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section-title span {
  display: inline-block;
}
.section-title-small {
  font-size: 12px;
  color: #a0a7b3;
}
.btn-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.btn {
  flex: 1 1 48%;
  padding: 10px 8px;
  border-radius: 10px;
  border: none;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.btn-on  { background:#3fb983; color:#071017; }
.btn-off { background:#e45858; color:#fff; }
.btn-sub { background:#2f3844; color:#e0e5ee; }
.btn:active {
  transform: scale(0.97);
  background:#f5f5f5;
  color:#111315;
}
/* 버튼이 눌렸을 때 JS가 적용하는 '흰색 번쩍' 효과 */
.btn.flash,
.small-btn.flash {
  background: #f5f5f5 !important;
  color: #111315 !important;
}
.device-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 2px;
  border-top: 1px solid #20252d;
  font-size: 12px;
}
.device-main {
  display: flex;
  align-items: center;
}
.dot {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  margin-right: 6px;
}
.dot.on {
  background: #6dc36d;
}
.dot.off {
  background: #a9b2ba;
}
.dot.error {
  background: #e45858;
}
.device-texts {
  display: flex;
  flex-direction: column;
}
.device-name { font-size: 13px; }
.device-ip   { font-size: 11px; color:#8b95a3; }
.device-extra{ font-size: 11px; color:#c0cad5; }
.btn-group-right {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: flex-end;
}
.small-btn {
  padding: 5px 8px;
  border-radius: 7px;
  border: none;
  font-size: 12px;
  min-width: 44px;
}
.small-on  { background:#3fb983; color:#071017; }
.small-off { background:#e45858; color:#fff; }
.small-sub { background:#2f3844; color:#e0e5ee; }
.small-btn:active {
  transform: scale(0.97);
  background:#f5f5f5;
  color:#111315;
}
.schedule-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
  margin-bottom: 6px;
}
.schedule-grid button {
  padding: 4px 0;
  font-size: 11px;
  border-radius: 6px;
  border: none;
}
.schedule-grid button.on {
  background:#3fb983;
  color:#071017;
}
.schedule-grid button.off {
  background:#2f3844;
  color:#c0cad5;
}
.time-row {
  display:flex;
  align-items:center;
  justify-content:space-between;
  margin-top:4px;
}
.time-row label {
  font-size:12px;
  color:#c7ced8;
}
.time-row input[type="time"] {
  width: 160px;   /* 시간 입력 박스 */
  padding: 6px 30px 6px 8px;
  box-sizing: border-box;
  border-radius: 6px;
  border: 1px solid #343b45;
  background:
    linear-gradient(to right, #111315 0%, #111315 70%, #1f2733 70%, #1f2733 100%);
  color: #f5f5f5;
  font-size: 13px;
  text-align: left;
}

/* Reboot Delay 전용 스타일 */
#rebootDelay {
  width: 56px;
  padding: 4px 8px;
  box-sizing: border-box;
  border-radius: 6px;
  border: 1px solid #343b45;
  background: #111315;
  color: #f5f5f5;
  font-size: 13px;
  text-align: right;
}

.log-toggle {
  display:flex;
  align-items:center;
  margin-top:8px;
  font-size:12px;
  color:#c0cad5;
}
.log-toggle label {
  margin-left: 6px;
}
.log-box {
  margin-top:4px;
  max-height:140px;
  background:#101318;
  border-radius:8px;
  padding:6px;
  font-size:11px;
  overflow-y:auto;
  border:1px solid #20252d;
  white-space: pre-wrap;
  word-break: break-all;
}
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.75);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 999;
}
.overlay-inner {
  background: #181c22;
  padding: 18px 24px;
  border-radius: 12px;
  text-align: center;
  box-shadow: 0 8px 24px rgba(0,0,0,0.6);
}
.overlay-title {
  font-size: 14px;
  color: #a0a7b3;
  margin-bottom: 6px;
}
.overlay-main {
  font-size: 18px;
  font-weight: 600;
}
</style>
</head>
<body>
<div class="overlay" id="overlay">
  <div class="overlay-inner">
    <div class="overlay-title">Running...</div>
    <div class="overlay-main" id="overlayText">ALL ON</div>
  </div>
</div>
<div class="app">
  <div class="top-bar">
    <span id="nowText">--:--:--</span>
    <button class="top-btn" onclick="location.href='/remote'">REMOTE</button>
  </div>
  <div id="offlineBanner" class="offline-banner" style="display:none;">
    Disconnected from TotalScheduler server.
  </div>

  <div class="section">
    <div class="section-title">
      <span id="adminGroupTitle">Group Control</span>
    </div>
    <div class="btn-row">
      <button class="btn btn-on"  onclick="flashAndSend(this,'group_pc_on')">PC ON</button>
      <button class="btn btn-off" onclick="flashAndSend(this,'group_pc_off')">PC OFF</button>
      <button class="btn btn-on"  onclick="flashAndSend(this,'group_beam_on')">BEAM ON</button>
      <button class="btn btn-off" onclick="flashAndSend(this,'group_beam_off')">BEAM OFF</button>
      <button class="btn btn-on"  onclick="flashAndSend(this,'group_shutter_open')">Shutter OPEN</button>
      <button class="btn btn-off" onclick="flashAndSend(this,'group_shutter_close')">Shutter CLOSE</button>
    </div>
  </div>

  <div class="section">
    <div class="section-title"><span>PC Test</span></div>
    <div id="pcList"></div>
  </div>

  <div class="section">
    <div class="section-title"><span>Projector Test</span></div>
    <div id="beamList"></div>
  </div>

  <div class="section">
    <div class="section-title"><span>TCP Test</span></div>
    <div id="tcpList"></div>
  </div>

  <div class="section">
    <div class="section-title"><span>OSC Button Test</span></div>
    <div id="oscList"></div>
  </div>

  <div class="section">
    <div class="section-title">
      <span>Auto Schedule</span>
      <span class="section-title-small">
        <label><input type="checkbox" id="scheduleEnabled"> Enabled</label>
      </span>
    </div>
    <div class="schedule-grid" id="dayGrid"></div>
    <div class="time-row">
      <label>ALL ON</label>
      <input id="onTime" type="time" step="60">
    </div>
    <div class="time-row">
      <label>ALL OFF</label>
      <input id="offTime" type="time" step="60">
    </div>
    <div class="time-row">
      <label>Reboot</label>
      <div style="display:flex;align-items:center;justify-content:flex-end;gap:8px;">
        <label style="font-size:12px;">
          <input type="checkbox" id="rebootEnabled"> After ALL ON
        </label>
        <span style="font-size:12px;">Delay</span>
        <input id="rebootDelay" type="number" min="1" max="120" step="1" style="width:56px;">
        <span style="font-size:12px;">min</span>
      </div>
    </div>
    <div style="text-align:right; margin-top:8px;">
      <button class="btn btn-sub" style="flex:none; padding:8px 16px;" onclick="saveSchedule()">Save</button>
    </div>
  </div>

  <div class="section">
    <div class="section-title"><span>Log</span></div>
    <div class="log-toggle">
      <input type="checkbox" id="logLive" checked onchange="toggleLogLive()">
      <label for="logLive">Live update</label>
    </div>
    <div class="log-box" id="logBox"></div>
  </div>
</div>

<script>
const offlineBanner = document.getElementById("offlineBanner");
const logBox        = document.getElementById("logBox");
const logLive       = document.getElementById("logLive");

// Live log 체크 상태를 localStorage에서 복원
if (logLive) {
  try {
    const saved = window.localStorage.getItem("ts_log_live");
    if (saved === "0") {
      logLive.checked = false;
    } else if (saved === "1") {
      logLive.checked = true;
    }
  } catch (e) {
    console.log("localStorage get error", e);
  }
}

/* ★ 추가: 버튼 깜빡이기 공통 함수 */
function flashButton(btn) {
  if (!btn) return;
  btn.classList.add("flash");
  setTimeout(() => btn.classList.remove("flash"), 120);
}

function flashAndSend(btn, action, payload) {
  flashButton(btn);
  sendAction(action, payload);
}
/* ★ 여기까지 추가 */

let enabledDays = [true,true,true,true,true,true,false];  // Mon~Sun 기본
// -------------- 공통 액션 --------------
async function sendAction(action, payload) {
  try {
    await fetch("/api/action", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(Object.assign({action: action}, payload || {}))
    });
  } catch (e) {
    console.log("action error", e);
  }
}

// -------------- 리스트 렌더링 --------------
function makePcRow(parent, pc) {
  const row = document.createElement("div");
  row.className = "device-row";

  const main = document.createElement("div");
  main.className = "device-main";

  const dot = document.createElement("div");
  dot.className = "dot " + (pc.status || "off");
  main.appendChild(dot);

  const texts = document.createElement("div");
  texts.className = "device-texts";

  const name = document.createElement("div");
  name.className = "device-name";
  name.textContent = pc.name || "PC";

  const ip = document.createElement("div");
  ip.className = "device-ip";
  ip.textContent = pc.ip || "";

  texts.appendChild(name);
  texts.appendChild(ip);
  main.appendChild(texts);
  row.appendChild(main);

  const btns = document.createElement("div");
  btns.className = "btn-group-right";

  const onBtn  = document.createElement("button");
  const offBtn = document.createElement("button");
  const rbBtn  = document.createElement("button");

  onBtn.className  = "small-btn small-on";
  offBtn.className = "small-btn small-off";
  rbBtn.className  = "small-btn small-sub";

  onBtn.textContent  = "ON";
  offBtn.textContent = "OFF";
  rbBtn.textContent  = "Reboot";

  onBtn.onclick  = () => flashAndSend(onBtn, "pc_on",  {ip: pc.ip});
  offBtn.onclick = () => flashAndSend(offBtn, "pc_off", {ip: pc.ip});
  rbBtn.onclick  = () => flashAndSend(rbBtn,  "pc_reboot", {ip: pc.ip});

  btns.appendChild(onBtn);
  btns.appendChild(offBtn);
  btns.appendChild(rbBtn);
  row.appendChild(btns);

  parent.appendChild(row);
}

function makeBeamRow(parent, b) {
  const row = document.createElement("div");
  row.className = "device-row";

  const main = document.createElement("div");
  main.className = "device-main";

  const dot = document.createElement("div");
  dot.className = "dot " + (b.status || "off");
  main.appendChild(dot);

  const texts = document.createElement("div");
  texts.className = "device-texts";

  const name = document.createElement("div");
  name.className = "device-name";
  name.textContent = b.name || "Projector";

  const ip = document.createElement("div");
  ip.className = "device-ip";
  ip.textContent = (b.ip || "") + ":" + (b.port || 4352);

  const extra = document.createElement("div");
  extra.className = "device-extra";
  if (b.shutter) {
    extra.textContent = "Shutter: " + b.shutter.toUpperCase();
  } else {
    extra.textContent = "";
  }

  texts.appendChild(name);
  texts.appendChild(ip);
  texts.appendChild(extra);
  main.appendChild(texts);
  row.appendChild(main);

  const btns = document.createElement("div");
  btns.className = "btn-group-right";

  function small(label, cls, action, params) {
    const bt = document.createElement("button");
    bt.className = "small-btn " + cls;
    bt.textContent = label;
    bt.onclick = () => flashAndSend(bt, action, params);
    return bt;
  }

  btns.appendChild(small("ON",   "small-on",  "beam_on",  {ip: b.ip, port: b.port}));
  btns.appendChild(small("OFF",  "small-off", "beam_off", {ip: b.ip, port: b.port}));
  btns.appendChild(small("Open", "small-sub", "beam_shutter_open",  {ip: b.ip, port: b.port}));
  btns.appendChild(small("Close","small-sub", "beam_shutter_close", {ip: b.ip, port: b.port}));

  row.appendChild(btns);
  parent.appendChild(row);
}

function makeTcpRow(parent, t) {
  const row = document.createElement("div");
  row.className = "device-row";

  const main = document.createElement("div");
  main.className = "device-main";

  const dot = document.createElement("div");
  dot.className = "dot off";
  main.appendChild(dot);

  const texts = document.createElement("div");
  texts.className = "device-texts";

  const name = document.createElement("div");
  name.className = "device-name";
  name.textContent = t.name || "TCP";

  const ip = document.createElement("div");
  ip.className = "device-ip";
  ip.textContent = t.ip + ":" + t.port;

  texts.appendChild(name);
  texts.appendChild(ip);
  main.appendChild(texts);
  row.appendChild(main);

  const btns = document.createElement("div");
  btns.className = "btn-group-right";

  const btn = document.createElement("button");
  btn.className = "small-btn small-sub";
  btn.textContent = "Send";
  btn.onclick = () => flashAndSend(btn, "tcp_send", {index: t.index});

  btns.appendChild(btn);
  row.appendChild(btns);
  parent.appendChild(row);
}

function makeOscRow(parent, o) {
  const row = document.createElement("div");
  row.className = "device-row";

  const main = document.createElement("div");
  main.className = "device-main";

  const dot = document.createElement("div");
  dot.className = "dot off";
  main.appendChild(dot);

  const texts = document.createElement("div");
  texts.className = "device-texts";

  const name = document.createElement("div");
  name.className = "device-name";
  name.textContent = o.label || ("OSC " + (o.index + 1));

  const ip = document.createElement("div");
  ip.className = "device-ip";
  ip.textContent = o.ip + ":" + o.port + " " + o.address;

  texts.appendChild(name);
  texts.appendChild(ip);
  main.appendChild(texts);
  row.appendChild(main);

  const btns = document.createElement("div");
  btns.className = "btn-group-right";

  const btn = document.createElement("button");
  btn.className = "small-btn small-sub";
  btn.textContent = "Send";
  btn.onmousedown  = () => { flashButton(btn); sendAction("osc_press",   {index: o.index}); };
  btn.onmouseup    = () => { sendAction("osc_release", {index: o.index}); };

  btn.ontouchstart = (e) => {
    e.preventDefault();
    flashButton(btn);
    sendAction("osc_press", {index: o.index});
  };
  btn.ontouchend   = (e) => {
    e.preventDefault();
    sendAction("osc_release", {index: o.index});
  };

  btns.appendChild(btn);
  row.appendChild(btns);
  parent.appendChild(row);
}

// -------------- Auto Schedule --------------
function renderDayButtons() {
  const labels = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
  const grid = document.getElementById("dayGrid");
  grid.innerHTML = "";
  enabledDays.forEach((v, idx) => {
    const btn = document.createElement("button");
    btn.textContent = labels[idx];
    btn.className = v ? "on" : "off";
    btn.onclick = () => {
      enabledDays[idx] = !enabledDays[idx];
      renderDayButtons();
    };
    grid.appendChild(btn);
  });
}

async function loadSchedule() {
  try {
    const res = await fetch("/api/schedule");
    if (!res.ok) throw new Error("http " + res.status);
    const cfg = await res.json();

    const ed = cfg.enabled_days;
    if (Array.isArray(ed) && ed.length === 7) {
      enabledDays = ed.slice();
    }

    const onTime      = document.getElementById("onTime");
    const offTime     = document.getElementById("offTime");
    const enChk       = document.getElementById("scheduleEnabled");
    const rebootChk   = document.getElementById("rebootEnabled");
    const rebootDelay = document.getElementById("rebootDelay");

    if (onTime)  onTime.value  = cfg.all_on_time  || "09:00";
    if (offTime) offTime.value = cfg.all_off_time || "18:00";
    if (enChk)   enChk.checked = cfg.enabled !== false;

    if (rebootChk) {
      rebootChk.checked = !!cfg.reboot_after_on_enabled;
    }
    if (rebootDelay) {
      let d = 5;
      if (typeof cfg.reboot_delay_min === "number") {
        d = cfg.reboot_delay_min;
      } else if (typeof cfg.reboot_delay_min === "string") {
        const parsed = parseInt(cfg.reboot_delay_min, 10);
        if (!isNaN(parsed)) d = parsed;
      }
      if (!Number.isFinite(d) || d < 1) d = 5;
      if (d > 120) d = 120;
      rebootDelay.value = d;
    }

    renderDayButtons();
  } catch (e) {
    console.log("loadSchedule error", e);
  }
}

async function saveSchedule() {
  const onTime      = document.getElementById("onTime");
  const offTime     = document.getElementById("offTime");
  const enChk       = document.getElementById("scheduleEnabled");
  const rebootChk   = document.getElementById("rebootEnabled");
  const rebootDelay = document.getElementById("rebootDelay");

  let delayMin = 5;
  if (rebootDelay && rebootDelay.value) {
    const v = parseInt(rebootDelay.value, 10);
    if (!isNaN(v)) {
      delayMin = v;
    }
  }
  if (delayMin < 1) delayMin = 1;
  if (delayMin > 120) delayMin = 120;

  const body = {
    enabled: !!(enChk && enChk.checked),
    enabled_days: enabledDays.slice(),
    all_on_time: (onTime && onTime.value) || "09:00",
    all_off_time: (offTime && offTime.value) || "18:00",
    reboot_after_on_enabled: !!(rebootChk && rebootChk.checked),
    reboot_delay_min: delayMin
  };

  try {
    await fetch("/api/schedule", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    });
  } catch (e) {
    console.log("saveSchedule error", e);
  }
}

// -------------- 로그 --------------
function toggleLogLive() {
  if (!logLive) return;
  try {
    window.localStorage.setItem("ts_log_live", logLive.checked ? "1" : "0");
  } catch (e) {
    console.log("localStorage set error", e);
  }
}

async function pollLogs() {
  try {
    const res = await fetch("/api/logs?limit=100");
    if (!res.ok) throw new Error("http " + res.status);
    const data = await res.json();
    if (!logLive || !logLive.checked) return;
    if (Array.isArray(data)) {
      logBox.textContent = data.join("\\n");
      logBox.scrollTop = logBox.scrollHeight;
    }
  } catch (e) {
    console.log("log error", e);
  } finally {
    setTimeout(pollLogs, 2000);
  }
}

// -------------- 상태 폴링 --------------
async function pollState() {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 4000);
    const res = await fetch("/api/state?full=1", {signal: controller.signal});
    clearTimeout(timer);

    if (!res.ok) throw new Error("http " + res.status);
    const data = await res.json();

    offlineBanner.style.display = "none";
    updateState(data);
  } catch (e) {
    console.log("state error", e);
    offlineBanner.style.display = "block";
  } finally {
    setTimeout(pollState, 1000);
  }
}

function updateState(data) {
  const nowEl = document.getElementById("nowText");
  if (nowEl) nowEl.textContent = data.now || "";

  // ★ 추가: ADMIN Group Control 제목 동적 변경
  const adminGroupTitleEl = document.getElementById("adminGroupTitle");
  if (adminGroupTitleEl && data.web_group_title) {
    adminGroupTitleEl.textContent = data.web_group_title;
  }
  
  const ov  = document.getElementById("overlay");
  const txt = document.getElementById("overlayText");
  if (data.busy) {
    ov.style.display = "flex";
    txt.textContent = data.busy_name || "Running";
  } else {
    ov.style.display = "none";
  }

  const pcList   = document.getElementById("pcList");
  const beamList = document.getElementById("beamList");
  const tcpList  = document.getElementById("tcpList");
  const oscList  = document.getElementById("oscList");

  if (pcList) {
    pcList.innerHTML = "";
    (data.pcs || []).forEach(pc => makePcRow(pcList, pc));
  }
  if (beamList) {
    beamList.innerHTML = "";
    (data.projectors || []).forEach(b => makeBeamRow(beamList, b));
  }
  if (tcpList) {
    tcpList.innerHTML = "";
    (data.tcp_outputs || []).forEach(t => makeTcpRow(tcpList, t));
  }
  if (oscList) {
    oscList.innerHTML = "";
    (data.osc_buttons || []).forEach(o => makeOscRow(oscList, o));
  }
}

// -------------- 초기화 --------------
loadSchedule();
pollState();
pollLogs();
</script>
</body>
</html>
"""

        # ------------- routing -------------

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path in ("/", "/remote"):
                self._send_text(self._remote_page_html())
            elif path == "/admin":
                self._send_text(self._admin_page_html())
            elif path == "/api/state":
                self._handle_state(parsed)
            elif path == "/api/logs":
                self._handle_logs(parsed)
            elif path == "/api/schedule":
                self._handle_get_schedule()
            else:
                self._send_text("Not Found", status=404, content_type="text/plain; charset=utf-8")

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/action":
                self._handle_action()
            elif path == "/api/schedule":
                self._handle_post_schedule()
            else:
                self._send_text("Not Found", status=404, content_type="text/plain; charset=utf-8")

        # ------------- handlers -------------

        def _handle_state(self, parsed):
            qs = parse_qs(parsed.query)
            full = qs.get("full", ["0"])[0] == "1"

            snap = self.ctrl.get_state_snapshot()
            busy, name = self.ctrl.is_busy()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            resp = {
                "now": now,
                "busy": bool(busy),
                "busy_name": name,
                "pcs": [],
                "projectors": [],
                "web_group_title": self.ctrl.config.get("web_group_title", "Group Control"),
            }

            # PCs
            cfg_pcs = self.ctrl.config.get("pcs", [])
            state_pcs = snap.get("pcs", [])
            for pc in cfg_pcs:
                ip = pc.get("ip")
                st = next((p for p in state_pcs if p.get("ip") == ip), {})
                resp["pcs"].append({
                    "name": pc.get("name", ""),
                    "ip": ip,
                    "status": st.get("status", "off"),
                })

            # Projectors
            cfg_beams = self.ctrl.config.get("projectors", [])
            state_beams = snap.get("projectors", [])
            for b in cfg_beams:
                ip = b.get("ip")
                port = int(b.get("port", 4352) or 4352)
                st = next(
                    (x for x in state_beams if x.get("ip") == ip and int(x.get("port", 4352)) == port),
                    {},
                )
                resp["projectors"].append({
                    "name": b.get("name", ""),
                    "ip": ip,
                    "port": port,
                    "status": st.get("status", "off"),
                    "shutter": st.get("shutter", ""),
                })

            if full:
                # TCP outputs
                tcp_list = []
                for idx, t in enumerate(self.ctrl.config.get("tcp_outputs", [])):
                    tcp_list.append({
                        "index": idx,
                        "name": t.get("name", f"TCP {idx+1}"),
                        "ip": t.get("ip", ""),
                        "port": int(t.get("port", 0) or 0),
                    })
                resp["tcp_outputs"] = tcp_list

                # OSC buttons
                osc_list = []
                for idx, o in enumerate(self.ctrl.config.get("osc_buttons", [])):
                    if not o.get("enabled"):
                        continue
                    osc_list.append({
                        "index": idx,
                        "label": o.get("label") or f"OSC {idx+1}",
                        "ip": o.get("ip", ""),
                        "port": int(o.get("port", 0) or 0),
                        "address": o.get("address", ""),
                    })
                resp["osc_buttons"] = osc_list

                # Schedule
                sch = self.ctrl.config.get("schedule", {})
                if "enabled" not in sch:
                    sch["enabled"] = True
                resp["schedule"] = sch

            self._send_json(resp)

        def _handle_logs(self, parsed):
            qs = parse_qs(parsed.query)
            try:
                limit = int(qs.get("limit", ["100"])[0])
            except Exception:
                limit = 100
            lines = []
            if hasattr(self.ctrl, "get_recent_logs"):
                try:
                    lines = self.ctrl.get_recent_logs(limit)
                except Exception:
                    lines = []
            self._send_json(lines)

        def _handle_get_schedule(self):
            sch = self.ctrl.config.setdefault("schedule", {})
            # 기본값 보정
            if "enabled" not in sch:
                sch["enabled"] = True
            days = sch.get("enabled_days")
            if not isinstance(days, list) or len(days) != 7:
                sch["enabled_days"] = [True, True, True, True, True, True, False]
            if "all_on_time" not in sch:
                sch["all_on_time"] = "09:00"
            if "all_off_time" not in sch:
                sch["all_off_time"] = "18:00"
            if "reboot_after_on_enabled" not in sch:
                sch["reboot_after_on_enabled"] = False
            if "reboot_delay_min" not in sch:
                sch["reboot_delay_min"] = 5
            self._send_json(sch)

        def _handle_post_schedule(self):
            body = self._read_json()
            sch = self.ctrl.config.setdefault("schedule", {})

            enabled = body.get("enabled")
            if isinstance(enabled, bool):
                sch["enabled"] = enabled

            enabled_days = body.get("enabled_days")
            if isinstance(enabled_days, list) and len(enabled_days) == 7:
                sch["enabled_days"] = [bool(x) for x in enabled_days]

            on = body.get("all_on_time")
            off = body.get("all_off_time")
            if isinstance(on, str) and ":" in on:
                sch["all_on_time"] = on
            if isinstance(off, str) and ":" in off:
                sch["all_off_time"] = off

            reboot_enabled = body.get("reboot_after_on_enabled")
            if isinstance(reboot_enabled, bool):
                sch["reboot_after_on_enabled"] = reboot_enabled

            reboot_delay = body.get("reboot_delay_min")
            if reboot_delay is not None:
                try:
                    d = int(reboot_delay)
                except Exception:
                    d = 5
                if d < 1:
                    d = 1
                if d > 120:
                    d = 120
                sch["reboot_delay_min"] = d

            self.ctrl.log(f"WebUI schedule updated: {sch}")

            # --- AutoScheduler 실행 이력 초기화 (WebUI에서 스케줄 수정 시) ---
            sched = getattr(self.ctrl, "scheduler", None)
            if sched and hasattr(sched, "reset_fired_dates"):
                try:
                    sched.reset_fired_dates()
                except Exception as e:
                    self.ctrl.log(f"Scheduler reset error (web): {e}")

            self.ctrl.save_config()
            self._send_json({"ok": True})

        def _handle_action(self):
            data = self._read_json()
            action = data.get("action")
            if not action:
                self._send_json({"ok": False, "error": "no action"}, status=400)
                return

            c = self.ctrl

            # Group actions
            if action == "all_on":
                c.run_async("ALL ON (Web)", c.all_on)
            elif action == "all_off":
                c.run_async("ALL OFF (Web)", c.all_off)
            elif action == "group_pc_on":
                c.run_async("PC ALL ON (Web)", c.group_pc_on)
            elif action == "group_pc_off":
                c.run_async("PC ALL OFF (Web)", c.group_pc_off)
            elif action == "group_beam_on":
                c.run_async("BEAM ALL ON (Web)", c.group_beam_on)
            elif action == "group_beam_off":
                c.run_async("BEAM ALL OFF (Web)", c.group_beam_off)
            elif action == "group_shutter_open":
                c.run_async("SHUTTER OPEN ALL (Web)", c.group_shutter_open)
            elif action == "group_shutter_close":
                c.run_async("SHUTTER CLOSE ALL (Web)", c.group_shutter_close)

            # Individual PCs
            elif action in ("pc_on", "pc_off", "pc_reboot"):
                ip = data.get("ip")
                if ip:
                    if action == "pc_on":
                        c.run_async(f"PC ON {ip} (Web)", c.pc_on, ip)
                    elif action == "pc_off":
                        c.run_async(f"PC OFF {ip} (Web)", c.pc_off, ip)
                    elif action == "pc_reboot":
                        c.run_async(f"PC REBOOT {ip} (Web)", c.pc_reboot, ip)

            # Individual projectors
            elif action in ("beam_on", "beam_off", "beam_shutter_open", "beam_shutter_close"):
                ip = data.get("ip")
                port = data.get("port")
                if ip:
                    if port is None:
                        target = getattr(c, action)
                        c.run_async(f"{action} {ip} (Web)", target, ip)
                    else:
                        try:
                            p = int(port)
                        except Exception:
                            p = None
                        if p is not None:
                            target = getattr(c, action)
                            c.run_async(f"{action} {ip}:{p} (Web)", target, ip, p)

            # TCP test
            elif action == "tcp_send":
                try:
                    idx = int(data.get("index", -1))
                except Exception:
                    idx = -1
                arr = c.config.get("tcp_outputs", [])
                if 0 <= idx < len(arr):
                    t = arr[idx]
                    ip = t.get("ip")
                    try:
                        port = int(t.get("port", 0) or 0)
                    except Exception:
                        port = 0
                    payload = t.get("data", "")
                    if ip and port and payload:
                        # 웹에서 TCP 테스트는 짧게 끝나는 작업이므로
                        # busy 오버레이를 사용하지 않고 바로 전송만 수행
                        c._tcp_send(
                            ip,
                            port,
                            payload.encode("utf-8", errors="ignore"),
                        )

            # OSC buttons
            elif action in ("osc_press", "osc_release"):
                try:
                    idx = int(data.get("index", -1))
                except Exception:
                    idx = -1
                if 0 <= idx < len(c.config.get("osc_buttons", [])):
                    phase = "press" if action == "osc_press" else "release"
                    c.run_async(
                        f"OSC {idx+1} {phase.upper()} (Web)",
                        c.send_osc_index,
                        idx,
                        phase,
                    )

            else:
                self._send_json({"ok": False, "error": "unknown action"}, status=400)
                return

            self._send_json({"ok": True})

    return WebUIHandler


def start_web_server(controller, host: str = "0.0.0.0", port: int = DEFAULT_WEB_PORT):
    """
    Start the WebUI HTTP server in a background thread.
    """
    controller.log(f"DEBUG: start_web_server() called with host={host}, port={port}")

    handler_cls = make_handler(controller)
    try:
        httpd = ThreadingHTTPServer((host, port), handler_cls)
    except Exception as e:
        controller.log(f"WebUI start failed on {host}:{port} -> {e}")
        return None

    # serve_forever를 래핑해서, 예외가 나면 로그에 남기도록
    def _serve():
        try:
            httpd.serve_forever()
        except Exception as e:
            controller.log(f"WebUI server crashed: {e}")

    th = threading.Thread(target=_serve, daemon=True)
    th.start()
    controller.log(f"WebUI server started on http://{host}:{port}/remote")
    return th


