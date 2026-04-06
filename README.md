# TotalScheduler V2.1 - [DEMO]

> Python-based **Windows** integrated control system for PCs, projectors, relays, and media playback environments.  
> Designed for museum installations, exhibitions, and AV system automation.

---

## Copyright

© 2026 CreDL MEDIA Co., Ltd.
📧 [antonio@credl.net](mailto:antonio@credl.net)

---

## Features

### Demo Version

* PC control (Wake-on-LAN, RemotePower integration)
* Projector (BEAM) control via PJLink (Power & Shutter)
* TCP/UDP command output

  * (e.g., sequential power control via TCP relay)
* OSC button & slider control (supports media cue triggering)
* Time-based OSC triggers

  * (e.g., scheduled content playback, LED brightness control)
* Weekly auto scheduling (ALL ON / ALL OFF)
* Built-in Web Server for monitoring via mobile/tablet (local network)
* Demo available for 2 weeks
* Reusable by refreshing `trial.json`

---

### PRO Version (Paid)

* Unlimited usage (no time restriction)
* Remote access from external networks via proxy gateway (with authentication)
* Mobile notifications for system errors
* Optional: Zigbee smart plug control

  * (TV power, work lights, LED systems, etc.)
* Optional: Server room temperature & humidity monitoring
* Requires license key authentication
* License is bound to a specific PC
* Currently available **only in Korea** (requires system setup support)

---

## Installation & Setup

### 1. Remote PC Setup

* Extract `RemotePowerV2.zip` to:

  ```
  C:\RemotePowerV2
  ```

* Run:

  ```
  install_all.bat (Run as Administrator)
  ```

* This installs:

  * **RemotePowerService** (Windows Service)
  * **RemoteState** (System tray application)

* Additional actions:

  * Opens required network ports
  * Registers RemoteState in startup

* When running:

  * A green power icon appears in the system tray
  * Hover to view IP / Port / MAC address
  * Click icon → shows "Exit" menu

---

### 2. Main PC Setup
> 💡 Tip: A mini PC is sufficient for the main control PC. (ex: N150)  

* Run:

  ```
  TotalScheduler.exe
  ```

* On first launch:

  * Windows Firewall / Security popup may appear
  * Select **Private Network** and allow access
  * Copyright notice appears once
  * `.config` folder is automatically created

* Configure devices:

  * Go to **Setup page**
  * Register PCs, projectors, and other devices
  
<img width="1705" height="1213" alt="mainui1" src="https://github.com/user-attachments/assets/51e7b379-06e4-4c3d-84d4-568953032fd4" />

---

## Web Server Access

* Same PC:

  ```
  http://127.0.0.1:9999/remote
  ```

* Other devices (mobile/tablet):

  ```
  http://<PC_IP>:9999/remote
  ```

  Example:

  ```
  http://192.168.0.100:9999/remote
  ```
<img width="376" height="830" alt="webui1" src="https://github.com/user-attachments/assets/22f2f781-45cc-4fab-b74c-a4b54a33cb04" />
<img width="376" height="1300" alt="webui2" src="https://github.com/user-attachments/assets/28c61621-ca45-4864-8ddd-f943f700aada" />

---

## Troubleshooting

* If Web UI is not accessible:

  * Check Windows Firewall settings
  * Allow inbound TCP port **9999**

---

## Additional Documentation

> For detailed instructions and advanced usage,
> please refer to `HowTo.txt`

