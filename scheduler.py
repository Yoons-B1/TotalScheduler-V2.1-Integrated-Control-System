import threading
import time
import datetime


class AutoScheduler(threading.Thread):
    def __init__(self, controller):
        super().__init__(daemon=True)
        self.ctrl = controller
        self._stop = threading.Event()
        # 하루에 한 번 실행 여부 기록 (on/off 각각)
        self.last_fired_date = {"on": None, "off": None}
        # 스케줄러가 시작된 시각
        # → 앱 재시작 시, 이미 과거에 지나간 스케줄이 바로 실행되는 것을 막기 위함
        self.started_at = datetime.datetime.now()

    def stop(self):
        self._stop.set()

    def reset_fired_dates(self):
        """
        사용자가 스케줄 ON/OFF 시간을 수정했을 때,
        같은 날에도 다시 테스트할 수 있도록 실행 이력을 초기화하되,
        이미 '현재 시각보다 이전'인 스케줄은 다시 실행되지 않도록
        오늘 실행한 것으로 표시한다.
        """
        now = datetime.datetime.now()
        self.last_fired_date = {"on": None, "off": None}

        cfg = self.ctrl.config.get("schedule", {})

        def parse_time(key, default_str):
            tstr = str(cfg.get(key, default_str) or default_str)
            try:
                h, m = tstr.split(":", 1)
                h = int(h)
                m = int(m)
            except Exception:
                if "on" in key:
                    h, m = 9, 0
                else:
                    h, m = 18, 0
            h = max(0, min(23, h))
            m = max(0, min(59, m))
            return now.replace(hour=h, minute=m, second=0, microsecond=0)

        on_at = parse_time("all_on_time", "09:00")
        off_at = parse_time("all_off_time", "18:00")

        # 이미 현재 시각보다 과거인 스케줄은
        # → 오늘 한 번 실행된 것으로 간주해서 다시 안 돌게 막는다.
        today = now.date()
        if on_at < now:
            self.last_fired_date["on"] = today
        if off_at < now:
            self.last_fired_date["off"] = today

        try:
            self.ctrl.log("[Scheduler] Fired-date history reset.")
        except Exception:
            pass

    def run(self):
        # 하루에 한 번만 실행되도록 기록

        while not self._stop.is_set():
            try:
                cfg = self.ctrl.config.get("schedule", {})

                # 전체 Enable 플래그 (없으면 True로 간주)
                if not cfg.get("enabled", True):
                    time.sleep(1.0)
                    continue

                # 요일 배열 정리
                enabled_days = cfg.get("enabled_days", [True] * 7)
                if len(enabled_days) != 7:
                    enabled_days = (list(enabled_days) + [True] * 7)[:7]

                now = datetime.datetime.now()
                dow = now.weekday()  # 0 = Mon

                if not enabled_days[dow]:
                    time.sleep(1.0)
                    continue

                def parse_time(key, default_str):
                    raw = cfg.get(key, default_str)
                    try:
                        # Case ① WebUI 저장: 문자열 "20:40" 형태
                        if isinstance(raw, str):
                            h, m = raw.split(":", 1)
                            return now.replace(hour=int(h), minute=int(m),
                                               second=0, microsecond=0)

                        # Case ② 메인앱에서 저장될 수 있는 (튜플/리스트) 형태
                        if isinstance(raw, (list, tuple)) and len(raw) == 2:
                            h, m = raw
                            return now.replace(hour=int(h), minute=int(m),
                                               second=0, microsecond=0)

                        # Case ③ datetime.time 형태로 저장된 상황 대비
                        if isinstance(raw, datetime.time):
                            return now.replace(hour=raw.hour, minute=raw.minute,
                                               second=0, microsecond=0)

                        # Case ④ dict 형태 저장 대비  {"hour":20,"minute":40}
                        if isinstance(raw, dict) and "hour" in raw and "minute" in raw:
                            return now.replace(hour=int(raw["hour"]), minute=int(raw["minute"]),
                                               second=0, microsecond=0)

                    except Exception:
                        pass

                    # ⑤ 파싱 실패 시 기본값 사용
                    h, m = map(int, default_str.split(":"))
                    return now.replace(hour=h, minute=m, second=0, microsecond=0)

                on_at = parse_time("all_on_time", "09:00")
                off_at = parse_time("all_off_time", "18:00")

                # 스케줄 옵션: ALL ON 후 PC 자동 재부팅 여부 + 딜레이(분)
                reboot_enabled = bool(cfg.get("reboot_after_on_enabled", False))
                reboot_delay_min = cfg.get("reboot_delay_min", 5)
                try:
                    reboot_delay_min = int(reboot_delay_min)
                except Exception:
                    reboot_delay_min = 5
                if reboot_delay_min < 1:
                    reboot_delay_min = 1
                if reboot_delay_min > 120:
                    reboot_delay_min = 120

                def should_fire(tag, target_dt):
                    if target_dt is None:
                        return False

                    # 🔒 앱을 다시 켰을 때,
                    # 스케줄러 시작 이전에 이미 지나간 시간(과거 스케줄)은
                    # 바로 다시 실행되지 않도록 막는다.
                    if target_dt < self.started_at:
                        return False

                    today = now.date()
                    # 오늘 이미 한 번 실행했으면 패스
                    if self.last_fired_date.get(tag) == today:
                        return False

                    delta_sec = (now - target_dt).total_seconds()
                    #   1) 지금 시간이 target 이후여야 하고 (delta>=0)
                    #   2) target 이후 15분(900초) 이내일 때만 실행
                    if 0 <= delta_sec <= 15 * 60:
                        self.last_fired_date[tag] = today
                        return True
                    return False

                if should_fire("on", on_at):
                    self.ctrl.log(f"AutoScheduler: ALL ON at {on_at.strftime('%H:%M')}")
                    self.ctrl.run_async("ALL ON (Auto)", self.ctrl.all_on)

                    if reboot_enabled:
                        # ALL ON 후 지정된 시간(분) 뒤 PC 순차 재부팅 + 그 후 5분 뒤 상태 체크
                        def _reboot_job():
                            try:
                                time.sleep(reboot_delay_min * 60)
                                self.ctrl.log(
                                    f"AutoScheduler: group PC REBOOT after ALL ON "
                                    f"(delay {reboot_delay_min} min)"
                                )
                                self.ctrl.group_pc_reboot()

                                # 재부팅 후 5분 뒤에도 안 켜진 PC/BEAM 알림
                                try:
                                    self.ctrl.schedule_post_all_on_check(delay_sec=300)
                                except Exception as e:
                                    self.ctrl.log(
                                        f"schedule_post_all_on_check failed (after reboot): {e}"
                                    )
                            except Exception as e:
                                self.ctrl.log(f"AutoScheduler reboot job error: {e}")

                        threading.Thread(target=_reboot_job, daemon=True).start()
                    else:
                        # 기존 동작: ALL ON 후 5분 뒤 체크
                        try:
                            self.ctrl.schedule_post_all_on_check(delay_sec=300)  # 5분
                        except Exception as e:
                            self.ctrl.log(f"schedule_post_all_on_check failed: {e}")

                if should_fire("off", off_at):
                    self.ctrl.log(f"AutoScheduler: ALL OFF at {off_at.strftime('%H:%M')}")
                    self.ctrl.run_async("ALL OFF (Auto)", self.ctrl.all_off)

            except Exception as e:
                self.ctrl.log(f"Scheduler error: {e}")

            time.sleep(0.5)
