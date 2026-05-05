[![Platform](https://img.shields.io/badge/platform-Windows-blue)](https://github.com/yoons100/TotalScheduler-V2.1-Integrated-Control-System/releases) [![Release](https://img.shields.io/badge/Release-V2.2--MS20-fc1ba6)](https://github.com/yoons100/TotalScheduler-V2.1-Integrated-Control-System/releases) [![License](https://img.shields.io/github/license/yoons100/TotalScheduler-V2.1-Integrated-Control-System)](https://github.com/yoons100/TotalScheduler-V2.1-Integrated-Control-System/blob/main/LICENSE)


# <img width="64" height="64" alt="total" src="https://github.com/user-attachments/assets/50c4bd65-1998-48be-b0b5-9c7bc7b12ffa" /> TotalScheduler V2 - [DEMO]

> 통합제어 시스템 - 토탈스케줄러V2가 MS스토어에 런칭했습니다.
>   
> 기존 설치방식은 2개의 보안메시지가 뜨게 됩니다.
> ```
> 1. 앱 다운로드 또는 압축해제시 : 신뢰할 수 없는 프로그램에 대한 보안경고
> 2. 첫 실행시 : 공용네트워크를 허용하는지 확인 메시지
> ```
> 두번째 메시지는 외부포트를 받을 때 사용자에게 미리 알리는 메시지 이지만,  
> 첫번째 메시지는 인증된 개발자가 만든 앱이 아니라는 경고로  
> 안티바이러스 프로그램에서 실행을 막고 파일을 지우는 경우도 생기게 됩니다.  
> 이것은 바이러스에 감염된 앱이 아니어도 공식 앱개발 인증서로 서명하지 않은 앱에서 생기는 문제 입니다.  
> (앱개발 인증서는 비용이 제법 나갑니다;;)  
> 이 문제를 해결하기 위해, MS스토어를 통해 공식인증서가 서명된 앱으로 배포하게 되었습니다.  
> MS스토어의 계정으로 로그인 해서 받아야 하는 불편함이 생겼지만,  
> 보안경고 없이, 자동업데이트를 지원해서 편리해진 점도 있습니다.  
> 양해해 주시기 바라며,  
> 앱뱃지 또는 아래 링크
를 통해 다운로드 가능합니다.

<a href="https://get.microsoft.com/installer/download/9np94q0d2m2r?referrer=appbadge" target="_self" >
	<img src="https://get.microsoft.com/images/en-us%20dark.svg" width="200"/>
</a>

https://apps.microsoft.com/detail/9NP94Q0D2M2R

---

## 개요
TotalScheduler는 PC, 빔프로젝터, 릴레이, 순차전원공급기 등을 관리하는 Python 기반의 통합 제어 시스템입니다.  
미술관, 전시장 등의 AV 시스템 자동화를 위해 설계되었습니다.

---

## 1. 포함 기능 [Demo]

- PC 제어 (WOL, RemotePowerV2 연동)  
- BEAM 제어 (PJLink: power & shutter)  
- TCP/UDP 명령 출력  
- OSC 버튼 및 슬라이더 제어  
- OSC 버튼 타임트리거 기능  
- 요일별 자동 ALL ON/OFF 스케줄링  
- WebServer 기반 내부망 모니터링  
- OSC 인풋 그룹 제어 (TouchOSC 활용)  
- 2주 데모 사용 가능  
- trial.json 갱신으로 재사용 가능  

### 유료 옵션 기능 [PRO]

- 기간 제한 없이 사용  
- 프록시보안 게이트웨이를 통한 외부망 접속 (보안 인증 가능)  
- 핸드폰으로 에러 상태 알림 메시지 수신  
- Zigbee 플러그 제어 (TV, 작업등, LED)  
- 서버룸 온도/습도 모니터링  
- 라이선스 키 인증 필요 (PC 귀속)  
- 유료기능[PRO]은 운영PC의 추가 설정이 필요하므로, 현재 **한국**에서만 서비스 됩니다 

---

## 2. RemotePowerV2 구조
제어되는 PC에 설치할 RemotePowerV2.zip을 다운 받으세요  
<a href="https://github.com/yoons100/TotalScheduler-V2.1-Integrated-Control-System/releases/download/V2.2-MS20/RemotePowerV2.zip">**Download RemotePowerV2.zip**</a>
```
RemotePowerV2.zip
├ RemotePowerService/
├ RemoteState/
├ install_all.bat  #관리자 권한으로 실행(서비스,모니터링앱 설치 및 포트셋업)
└ uninstall_all.bat
```

---

## 3. 사용 방법

### 첫 실행
- 메인PC에서 TotalScheduler V2실행 (필요시 시작프로그램에 등록 후 사용)
- 첫 실행시 보안관련 팝업이 뜰 수도 있음. 저작권 안내 팝업 1회 표시.
- Setup 페이지에서 "Download RemotePowerV2"를 눌러 PC제어용 파일을 제어PC에 복사.
- 제어되는 PC에 복사한 "RemotePowerV2.zip"을 압축풀어 C폴더에 넣고, "install_all.bat"을 관리자권한으로 실행.
- "RemotePowerService"가 윈도우서비스로 등록되며, "RemoteState"가 시스템 트레이에 생김
- 메인PC의 TotalSchedulerV2 앱에서 Setup 페이지 -> 장비 등록

### 장비 등록
Setup 페이지에서 아래 정보를 입력:

PC
- 이름
- IP
- MAC 주소 (WOL 필수)  
(리모트PC에서 시스템트레이 RemoteState아이콘(녹색 전원모양)에 마우스를 가져가면 IP/Port[5050]/MAC 확인가능)

프로젝터
- 이름
- IP
- 포트(기본 4352)
- PJLink 비밀번호(option, 비번이 없다면 그대로 둠)

TCP/UDP
- 명령 내용
- ON/OFF 시 사용 여부 설정

OSC 버튼/슬라이더
- 레이블(버튼이름)
- IP
- Port
- Address
- 타입(Button 또는 Slider)

입력 후 반드시 Save Settings 클릭

### 메인 페이지
- 각 장비 상태 표시
- 장비별 ON/OFF 가능
- 셔터제어가능(보임/숨김옵션제공, 키보드 좌,우 화살표로 매핑)
- 셔터제어 키보드 매핑은 앱이 최상위에 있을때만 적용됨(셋업페이지 Always on top 옵션)
- OSC 버튼/슬라이더 제어 가능(셋업페이지 체크박스 옵션체크)

### 스케줄링
- 요일 선택
- ALL ON 시간 설정
- ALL OFF 시간 설정
- 설정된 시간에 맞춰 자동 실행 

### WebServer
- 같은PC에서는 웹브라우저에 아래 주소로 접속  
  `http://127.0.0.1:9999/remote`
  
- 다른 디바이스(모바일/태블릿)에서는 해당 IP로 접속  
  `http://<PC_IP>:9999/remote`
  
예시:  
`http://192.168.0.100:9999/remote`

### 설정파일 경로
`C:\Users\[user name]\Documents\TotalScheduler\.config`

---

## 4. 주의사항
- 제어되는 PC의 방화벽에서 사용포트를 허용해야 함  
  (기본포트는 install_all.bat실행시 자동허용됨)  
  OSC(7000-7001, 9001), TCP(6000-6001) WebServer(9999)기본포트를 사용하지 않은 경우 해당포트를 허용해줘야 함. 
- 에러 혹은 오프라인일때는 장치앞에 빨간점이 보이고 핸드폰으로 에러메시지 수신 가능.(옵션)
- 팁 : 메인 PC는 미니PC로도 충분합니다(예: N150). 원격접속을 이용하면 모니터, 키보드, 마우스 없이도 운영 가능합니다. 

---

## 5. 문제 해결
[PC가 켜지지 않는 경우]
- MAC 주소 오타 확인
- BIOS Wake-on-LAN 활성화 여부 확인
- 윈도우즈 설정에 전원관리옵션 확인
- 장치관리자 네트워크 어댑터 WOL 설정 확인
- wol_repeat 값을 3~4로 조정

[프로젝터 제어 불가]
- IP/포트 확인
- PJLink 비밀번호 확인
- 네트워크 연결 상태 확인

[OSC 제어 불가]
- Address(/composition/...) 확인
- IP/Port 확인
- 방화벽 설정 확인(사용하려는 OSC포트를 인바운스 규칙추가)

[TCP/UDP 제어 불가]
- IP/Port확인
- String/Hex 전송모드 확인

---

## 6. 문의
(주)크리디엘미디어  
antonio@credl.net  

---

# TotalScheduler V2 [Demo Version]

## Overview
TotalScheduler is an integrated control system for managing PCs, projectors, relays, and sequential power controllers.  
It is designed for AV system automation in environments such as museums and exhibition spaces.

---

## 1. Features [Demo]

- PC control (WOL, RemotePowerV2 integration)  
- BEAM control (PJLink: power & shutter)  
- TCP/UDP command output (control sequential power relays, etc.)  
- OSC buttons and sliders (supports media software cues)  
- OSC button time trigger (scheduled content playback, LED brightness control, etc.)  
- Weekly automatic ALL ON/OFF scheduling  
- WebServer for internal network monitoring via mobile/tablet  
- Device group control via OSC input commands (TouchOSC compatible)  
- Demo version available for 14 days  
- Trial can be reset by renewing `trial.json`  

### Additional Features [PRO]

- Unlimited usage (no time restriction)  
- External mobile access via proxy server gateway (secure authentication supported)  
- Receive error status notifications on mobile devices  
- Zigbee plug control (TV power, work lights, LED power)  
- Server room temperature/humidity monitoring (sensor integration)  
- License key authentication required (license is bound to a specific PC)  
- Paid PRO features require additional setup on the control PC and are currently available **only in Korea**  

---

## 2. RemotePower Structure (PC Control)
Download RemotePowerV2.zip to install on the controlled PC  
<a href="https://github.com/yoons100/TotalScheduler-V2.1-Integrated-Control-System/releases/download/V2.2-MS20/RemotePowerV2.zip">**Download RemotePowerV2.zip**</a>
```
RemotePowerV2.zip
├ RemotePowerService/
├ RemoteState/
├ install_all.bat # Monitoring, signal receiving, port setup, startup registration (Run as Administrator)
└ uninstall_all.bat
```
---

## 3. Usage

### [First Run]

- Run TotalScheduler V2 on the main PC (register as startup if needed)  
- A security popup may appear on first run. Copyright notice is shown once  
- In Setup page, click **"Download RemotePowerV2"** and copy files to target PC  
- Extract `RemotePowerV2.zip` to `C:\` on the controlled PC  
- Run `install_all.bat` as Administrator  
- `RemotePowerService` is installed as a Windows service  
- `RemoteState` appears in the system tray  
- Register devices in the Setup page  

---

### [Device Registration]

Enter the following in Setup page:

#### PC
- Name  
- IP  
- MAC address (required for WOL)  

*(Hover over RemoteState tray icon (green power icon) to check IP / Port(5050) / MAC)*  

#### Projector
- Name  
- IP  
- Port (default: 4352)  
- PJLink password (optional)  

#### TCP/UDP
- Command data  
- Enable ON/OFF usage  

#### OSC Buttons / Sliders
- Label (button name)  
- IP  
- Port  
- Address  
- Type (Button or Slider)  

Make sure to click **Save Settings**

---

### [Main Page Usage]

- Displays device status  
- Individual ON/OFF control  
- Shutter control (show/hide option available, mapped to keyboard ← → keys)  
- Keyboard mapping works only when app is focused (use "Always on top" option)  
- OSC button/slider control available (enable in Setup page)  

---

### [Automatic Scheduling]

- Select weekdays  
- Set ALL ON time  
- Set ALL OFF time  
- Automatically executes based on schedule  

---

### [WebServer Remote Access]

- Same PC:  
  `http://127.0.0.1:9999/remote`

- Other devices (mobile/tablet):  
  `http://<PC_IP>:9999/remote`

Example:  
`http://192.168.0.100:9999/remote`

---

### [Configuration Path]
`C:\Users\[user name]\Documents\TotalScheduler\.config`

---

## 4. Notes & Tips

- Firewall must allow required ports (automatically configured when running install_all.bat)  
- If using non-default ports, allow manually:  
  OSC (7000-7001, 9001)  
  TCP (6000-6001)  
  WebServer (9999)  

- Red indicator = error or offline state  
- Mobile error notification available (PRO option)  

Tip:  
A mini PC (e.g., Intel N150) is sufficient for the main system.  
Remote access allows operation without monitor, keyboard, or mouse.  

---

## 5. Troubleshooting

### [PC not turning on]
- Check MAC address  
- Enable Wake-on-LAN in BIOS  
- Check Windows power management settings  
- Verify network adapter WOL settings  
- Increase `wol_repeat` to 3~4  

### [Projector not responding]
- Check IP/Port  
- Verify PJLink password  
- Check network connection  

### [OSC control not working]
- Check Address (/composition/...)  
- Verify IP/Port  
- Check firewall settings  

### [TCP/UDP control not working]
- Check IP/Port  
- Verify String/Hex mode  

---

## 6. Contact

CreDL MEDIA Co., Ltd.  
Email: antonio@credl.net  

---
