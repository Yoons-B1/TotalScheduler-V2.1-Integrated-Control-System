import threading
import time
import datetime


class AutoScheduler(threading.Thread):
    def __init__(self, controller):
        super().__init__(daemon=True)
        self.ctrl = controller
        self._stop = threading.Event()
        self.last_fired_date = {"on": None, "off": None}
        self.started_at = datetime.datetime.now()

    def stop(self):
        self._stop.set()

    def reset_fired_dates(self):
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

        while not self._stop.is_set():
            try:
                cfg = self.ctrl.config.get("schedule", {})

                if not cfg.get("enabled", True):
                    time.sleep(1.0)
                    continue

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
                        if isinstance(raw, str):
                            h, m = raw.split(":", 1)
                            return now.replace(hour=int(h), minute=int(m),
                                               second=0, microsecond=0)

                        if isinstance(raw, (list, tuple)) and len(raw) == 2:
                            h, m = raw
                            return now.replace(hour=int(h), minute=int(m),
                                               second=0, microsecond=0)

                        if isinstance(raw, datetime.time):
                            return now.replace(hour=raw.hour, minute=raw.minute,
                                               second=0, microsecond=0)

                        if isinstance(raw, dict) and "hour" in raw and "minute" in raw:
                            return now.replace(hour=int(raw["hour"]), minute=int(raw["minute"]),
                                               second=0, microsecond=0)

                    except Exception:
                        pass

                    h, m = map(int, default_str.split(":"))
                    return now.replace(hour=h, minute=m, second=0, microsecond=0)

                on_at = parse_time("all_on_time", "09:00")
                off_at = parse_time("all_off_time", "18:00")

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

                    if target_dt < self.started_at:
                        return False

                    today = now.date()
                    if self.last_fired_date.get(tag) == today:
                        return False

                    delta_sec = (now - target_dt).total_seconds()
                    if 0 <= delta_sec <= 15 * 60:
                        self.last_fired_date[tag] = today
                        return True
                    return False

                if should_fire("on", on_at):
                    self.ctrl.log(f"AutoScheduler: ALL ON at {on_at.strftime('%H:%M')}")
                    self.ctrl.run_async("ALL ON (Auto)", self.ctrl.all_on)

                    if reboot_enabled:
                        def _reboot_job():
                            try:
                                time.sleep(reboot_delay_min * 60)
                                self.ctrl.log(
                                    f"AutoScheduler: group PC REBOOT after ALL ON "
                                    f"(delay {reboot_delay_min} min)"
                                )
                                self.ctrl.group_pc_reboot()

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
                        try:
                            self.ctrl.schedule_post_all_on_check(delay_sec=300)  
                        except Exception as e:
                            self.ctrl.log(f"schedule_post_all_on_check failed: {e}")

                if should_fire("off", off_at):
                    self.ctrl.log(f"AutoScheduler: ALL OFF at {off_at.strftime('%H:%M')}")
                    self.ctrl.run_async("ALL OFF (Auto)", self.ctrl.all_off)

            except Exception as e:
                self.ctrl.log(f"Scheduler error: {e}")

            time.sleep(0.5)
