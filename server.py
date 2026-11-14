#!/usr/bin/env python3
import glob
import http.server
import json
import os
import re
import subprocess
import termios
import threading
import time
import urllib.request
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
DB_PATH = os.path.join(BASE_DIR, "cards.json")
HTTP_PORT = int(os.environ.get("RFID_PORT", "8080"))

DEFAULT_MP3 = os.environ.get("FONKINO_DEFAULT_AUDIO", "")

ACTION_PRESETS = [
    {
        "id": "lock_toggle",
        "label": "🔐 Akıllı Kilit (Açıkken Kilitle / Kilitliyken Aç)",
        "placeholder": "İsteğe bağlı bilgisayar şifresi (Boş bırakılırsa doğrudan oturum kilidini açar)",
        "defaultParam": ""
    },
    {
        "id": "unlock_screen",
        "label": "🔓 Kilitliyken Ekran Kilidini Aç (Şifre Gir / Aç)",
        "placeholder": "İsteğe bağlı bilgisayar şifresi (Boş bırakılırsa doğrudan kilidi açar)",
        "defaultParam": ""
    },
    {
        "id": "lock_screen",
        "label": "🔒 Bilgisayar Ekranını Kilitle",
        "placeholder": "Parametre gerekmez",
        "defaultParam": "lock"
    },
    {
        "id": "type_password",
        "label": "⌨️ Klavyeden Şifre / Metin Yaz + Enter'a Bas",
        "placeholder": "Kart okununca klavyeden otomatik yazılacak şifre veya metin",
        "defaultParam": ""
    },
    {
        "id": "open_url",
        "label": "🌐 Web Sitesi / URL Aç",
        "placeholder": "Örn: https://youtube.com veya https://github.com",
        "defaultParam": "https://www.youtube.com"
    },
    {
        "id": "play_sound",
        "label": "🎵 Müzik / Ses Çal - Durdur (Toggle)",
        "placeholder": "MP3/Ses dosya yolu veya boş bırakın (Varsayılan parça)",
        "defaultParam": DEFAULT_MP3 if os.path.exists(DEFAULT_MP3) else ""
    },
    {
        "id": "notify",
        "label": "🔔 Masaüstü Bildirimi Gönder",
        "placeholder": "Bildirim mesajı (Örn: Kart okundu, sistem hazır!)",
        "defaultParam": "Fonkino RFID: Kart okundu, sistem hazır!"
    },
    {
        "id": "volume_mute",
        "label": "🔇 Sistem Sesini Kapat / Aç (Mute Toggle)",
        "placeholder": "Parametre gerekmez",
        "defaultParam": "toggle"
    },
    {
        "id": "volume_set",
        "label": "🔊 Sistem Ses Seviyesini Ayarla (%)",
        "placeholder": "0 ile 150 arası ses yüzdesi (Örn: 80)",
        "defaultParam": "80"
    },
    {
        "id": "launch_app",
        "label": "🚀 Uygulama Başlat",
        "placeholder": "Uygulama komutu (Örn: brave, code, nautilus, kitty)",
        "defaultParam": "nautilus"
    },
    {
        "id": "webhook",
        "label": "🔗 HTTP Webhook / API İsteği Gönder",
        "placeholder": "Örn: https://ntfy.sh/fonkino-rfid",
        "defaultParam": "https://httpbin.org/post"
    },
    {
        "id": "shell_cmd",
        "label": "⚡ Özel Terminal / Bash Komutu Çalıştır",
        "placeholder": "Örn: notify-send 'Kart Okundu'",
        "defaultParam": "notify-send 'RFID Otomasyon' 'Özel komut başarıyla çalıştırıldı!'"
    },
    {
        "id": "none",
        "label": "📝 Sadece Kaydet / Logla (Fonksiyon Yok)",
        "placeholder": "Açıklama veya not (isteğe bağlı)",
        "defaultParam": ""
    }
]


def is_screen_locked():
    try:
        res = subprocess.run(
            ["qdbus6", "org.freedesktop.ScreenSaver", "/ScreenSaver", "org.freedesktop.ScreenSaver.GetActive"],
            capture_output=True,
            text=True,
            timeout=1.5
        )
        if res.returncode == 0 and res.stdout.strip().lower() == "true":
            return True
    except Exception:
        pass

    try:
        sid = os.environ.get("XDG_SESSION_ID", "")
        cmd = ["loginctl", "show-session"] + ([sid] if sid else []) + ["-p", "LockedHint", "--value"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
        if res.returncode == 0 and res.stdout.strip().lower() == "yes":
            return True
    except Exception:
        pass

    return False


def type_via_uinput(text, press_enter=True):
    import evdev
    from evdev import UInput, ecodes

    CHAR_MAP = {
        'a': (ecodes.KEY_A, False), 'b': (ecodes.KEY_B, False), 'c': (ecodes.KEY_C, False),
        'd': (ecodes.KEY_D, False), 'e': (ecodes.KEY_E, False), 'f': (ecodes.KEY_F, False),
        'g': (ecodes.KEY_G, False), 'h': (ecodes.KEY_H, False), 'i': (ecodes.KEY_I, False),
        'j': (ecodes.KEY_J, False), 'k': (ecodes.KEY_K, False), 'l': (ecodes.KEY_L, False),
        'm': (ecodes.KEY_M, False), 'n': (ecodes.KEY_N, False), 'o': (ecodes.KEY_O, False),
        'p': (ecodes.KEY_P, False), 'q': (ecodes.KEY_Q, False), 'r': (ecodes.KEY_R, False),
        's': (ecodes.KEY_S, False), 't': (ecodes.KEY_T, False), 'u': (ecodes.KEY_U, False),
        'v': (ecodes.KEY_V, False), 'w': (ecodes.KEY_W, False), 'x': (ecodes.KEY_X, False),
        'y': (ecodes.KEY_Y, False), 'z': (ecodes.KEY_Z, False),
        '1': (ecodes.KEY_1, False), '2': (ecodes.KEY_2, False), '3': (ecodes.KEY_3, False),
        '4': (ecodes.KEY_4, False), '5': (ecodes.KEY_5, False), '6': (ecodes.KEY_6, False),
        '7': (ecodes.KEY_7, False), '8': (ecodes.KEY_8, False), '9': (ecodes.KEY_9, False),
        '0': (ecodes.KEY_0, False),
        ' ': (ecodes.KEY_SPACE, False), '-': (ecodes.KEY_MINUS, False), '=': (ecodes.KEY_EQUAL, False),
        '.': (ecodes.KEY_DOT, False), ',': (ecodes.KEY_COMMA, False), '/': (ecodes.KEY_SLASH, False),
        '!': (ecodes.KEY_1, True), '@': (ecodes.KEY_2, True), '#': (ecodes.KEY_3, True),
        '$': (ecodes.KEY_4, True), '%': (ecodes.KEY_5, True), '^': (ecodes.KEY_6, True),
        '&': (ecodes.KEY_7, True), '*': (ecodes.KEY_8, True), '(': (ecodes.KEY_9, True),
        ')': (ecodes.KEY_0, True), '_': (ecodes.KEY_MINUS, True), '+': (ecodes.KEY_EQUAL, True),
        ':': (ecodes.KEY_SEMICOLON, True), ';': (ecodes.KEY_SEMICOLON, False),
    }

    all_keys = [
        ecodes.KEY_LEFTSHIFT, ecodes.KEY_ENTER, ecodes.KEY_SPACE, ecodes.KEY_BACKSPACE,
        ecodes.KEY_MINUS, ecodes.KEY_EQUAL, ecodes.KEY_DOT, ecodes.KEY_COMMA,
        ecodes.KEY_SLASH, ecodes.KEY_SEMICOLON
    ] + [getattr(ecodes, f"KEY_{c}") for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"]

    with UInput({ecodes.EV_KEY: all_keys}, name="OriginEdge-RFID-Keyboard") as ui:
        time.sleep(0.12)
        for ch in text:
            if ch.isupper() and ch.lower() in CHAR_MAP:
                key_code, _ = CHAR_MAP[ch.lower()]
                shift = True
            elif ch in CHAR_MAP:
                key_code, shift = CHAR_MAP[ch]
            else:
                continue

            if shift:
                ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1)
                ui.syn()
            ui.write(ecodes.EV_KEY, key_code, 1)
            ui.syn()
            time.sleep(0.015)
            ui.write(ecodes.EV_KEY, key_code, 0)
            ui.syn()
            if shift:
                ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
                ui.syn()
            time.sleep(0.015)

        if press_enter:
            ui.write(ecodes.EV_KEY, ecodes.KEY_ENTER, 1)
            ui.syn()
            time.sleep(0.02)
            ui.write(ecodes.EV_KEY, ecodes.KEY_ENTER, 0)
            ui.syn()


def unlock_desktop_session(password=""):
    sid = os.environ.get("XDG_SESSION_ID", "")
    if sid:
        subprocess.run(["loginctl", "unlock-session", sid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
    else:
        subprocess.run(["loginctl", "unlock-session"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)

    time.sleep(0.15)
    if is_screen_locked() and password:
        try:
            subprocess.run(
                ["sudo", "-S", "-k", "loginctl", "unlock-sessions"],
                input=password + "\n",
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.5
            )
        except Exception:
            pass

    time.sleep(0.1)
    if is_screen_locked() and password:
        try:
            type_via_uinput(password, press_enter=True)
        except Exception:
            pass


class ActionExecutor:
    def __init__(self):
        self.audio_proc = None
        self.lock = threading.Lock()

    def execute(self, card):
        action_type = (card.get("actionType") or "none").strip()
        param = (card.get("actionParam") or "").strip()
        uid = card.get("uid", "UNKNOWN")
        name = card.get("name") or uid

        if action_type == "none":
            return True, f"'{name}' ({uid}) okundu (Fonksiyon atanmamış, sadece kaydedildi)."

        try:
            if action_type == "lock_toggle":
                if is_screen_locked():
                    unlock_desktop_session(param)
                    return True, f"🔓 '{name}' ile bilgisayar kilidi açıldı!"
                else:
                    subprocess.Popen(
                        ["loginctl", "lock-session"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    return True, f"🔒 '{name}' ile bilgisayar ekranı kilitlendi!"

            elif action_type == "unlock_screen":
                unlock_desktop_session(param)
                return True, f"🔓 '{name}' okutuldu -> Kilit ekranı açıldı!"

            elif action_type == "lock_screen":
                subprocess.Popen(
                    ["loginctl", "lock-session"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return True, "🔒 Ekran kilitlendi."

            elif action_type == "type_password":
                if not param:
                    return False, "Yazılacak şifre/metin parametresi boş!"
                type_via_uinput(param, press_enter=True)
                return True, f"⌨️ '{name}' ile şifre/metin klavyeden girildi ve Enter'a basıldı!"

            elif action_type == "open_url":
                url = param if param else "https://www.google.com"
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url
                subprocess.Popen(
                    ["xdg-open", url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return True, f"🌐 URL açıldı: {url}"

            elif action_type == "play_sound":
                with self.lock:
                    if self.audio_proc is not None and self.audio_proc.poll() is None:
                        self.audio_proc.terminate()
                        try:
                            self.audio_proc.wait(timeout=0.5)
                        except Exception:
                            self.audio_proc.kill()
                        self.audio_proc = None
                        return True, "⏹️ Çalan müzik/ses durduruldu."

                    target = param if param else DEFAULT_MP3
                    if os.path.isfile(target):
                        self.audio_proc = subprocess.Popen(
                            ["mpv", "--no-video", target],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        return True, f"🎵 Müzik başlatıldı: {os.path.basename(target)}"
                    else:
                        snd = "/usr/share/sounds/freedesktop/stereo/complete.oga"
                        if os.path.isfile(snd):
                            subprocess.Popen(
                                ["paplay", snd],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                            )
                            return True, "🎵 Sistem bildirim sesi çalındı."
                        return False, f"Ses dosyası bulunamadı: {target}"

            elif action_type == "notify":
                msg = param if param else f"{name} ({uid}) okutuldu!"
                subprocess.Popen(
                    ["notify-send", "-a", "RFID Otomasyon", f"💳 {name}", msg],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return True, f"🔔 Bildirim gönderildi: {msg}"

            elif action_type == "volume_mute":
                subprocess.run(
                    ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2
                )
                return True, "🔇 Sistem sesi Mute/Unmute yapıldı."

            elif action_type == "volume_set":
                vol = max(0, min(150, int(float(param or "80"))))
                subprocess.run(
                    ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{vol}%"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2
                )
                return True, f"🔊 Sistem sesi %{vol} olarak ayarlandı."

            elif action_type == "launch_app":
                if not param:
                    return False, "Başlatılacak uygulama komutu boş!"
                subprocess.Popen(
                    param,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return True, f"🚀 Uygulama başlatıldı: {param}"

            elif action_type == "webhook":
                url = param if param else "https://httpbin.org/post"
                payload = json.dumps({
                    "uid": uid,
                    "name": name,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
                }).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/json", "User-Agent": "OriginEdge-RFID/1.0"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=4) as resp:
                    code = resp.getcode()
                return True, f"🔗 Webhook gönderildi ({url}) -> HTTP {code}"

            elif action_type == "shell_cmd":
                if not param:
                    return False, "Çalıştırılacak terminal komutu boş!"
                proc = subprocess.Popen(
                    param,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                try:
                    out, err = proc.communicate(timeout=3.0)
                    summary = (out or err or "").strip().splitlines()
                    first_line = f" ({summary[0][:60]})" if summary else ""
                    return True, f"⚡ Komut çalıştırıldı: {param}{first_line}"
                except subprocess.TimeoutExpired:
                    return True, f"⚡ Komut arka planda çalışıyor: {param}"

            return False, f"Bilinmeyen fonksiyon tipi: {action_type}"
        except Exception as e:
            return False, f"Fonksiyon hatası ({action_type}): {str(e)}"


executor = ActionExecutor()


class CardStore:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.cards = {}
        self.load()

    def load(self):
        with self.lock:
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            self.cards = {c["uid"].upper(): c for c in data if "uid" in c}
                        elif isinstance(data, dict):
                            self.cards = {k.upper(): v for k, v in data.items()}
                except Exception:
                    self.cards = {}
            else:
                self.cards = {}
                self._save_unlocked()

    def _save_unlocked(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(list(self.cards.values()), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_all(self):
        with self.lock:
            items = list(self.cards.values())
            items.sort(key=lambda x: x.get("lastScannedTs", 0), reverse=True)
            return items

    def get(self, uid):
        with self.lock:
            return self.cards.get(uid.upper())

    def upsert(self, card_data):
        with self.lock:
            uid = card_data.get("uid", "").strip().upper()
            if not uid:
                return None
            now_str = time.strftime("%Y-%m-%d %H:%M:%S")
            existing = self.cards.get(uid, {})
            merged = {
                "uid": uid,
                "name": card_data.get("name", existing.get("name", f"Kart {uid[-5:]}")).strip() or f"Kart {uid[-5:]}",
                "cardType": card_data.get("cardType", existing.get("cardType", "MIFARE")),
                "enabled": bool(card_data.get("enabled", existing.get("enabled", True))),
                "actionType": card_data.get("actionType", existing.get("actionType", "none")),
                "actionParam": card_data.get("actionParam", existing.get("actionParam", "")),
                "cooldownSec": float(card_data.get("cooldownSec", existing.get("cooldownSec", 2.0))),
                "scanCount": int(card_data.get("scanCount", existing.get("scanCount", 0))),
                "lastScannedAt": card_data.get("lastScannedAt", existing.get("lastScannedAt", "-")),
                "lastScannedTs": float(card_data.get("lastScannedTs", existing.get("lastScannedTs", 0.0))),
                "createdAt": existing.get("createdAt", now_str)
            }
            self.cards[uid] = merged
            self._save_unlocked()
            return merged

    def delete(self, uid):
        with self.lock:
            uid = uid.strip().upper()
            if uid in self.cards:
                del self.cards[uid]
                self._save_unlocked()
                return True
            return False


store = CardStore(DB_PATH)


class RfidSerialBridge:
    def __init__(self):
        self.fd = None
        self.port_path = "/dev/ttyUSB0"
        self.rx_buffer = ""
        self.lock = threading.Lock()
        self.paused = False
        self.auto_register = True
        self.last_trigger_by_uid = {}

        self.state = {
            "serialConnected": False,
            "serialPaused": False,
            "port": "/dev/ttyUSB0",
            "rfidOk": False,
            "version": "0x00",
            "antenna": "0x00",
            "uptime": 0,
            "lastStatusTs": 0,
            "lastScan": None,
            "lastInspect": None,
            "logs": []
        }

        self.running = True
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def add_log(self, text, level="info", uid=None):
        ts = time.strftime("%H:%M:%S")
        entry = {
            "id": int(time.time() * 1000),
            "time": ts,
            "text": text,
            "level": level,
            "uid": uid or ""
        }
        self.state["logs"].insert(0, entry)
        if len(self.state["logs"]) > 60:
            self.state["logs"].pop()

    def _find_port(self):
        candidates = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
        if candidates:
            return candidates[0]
        return "/dev/ttyUSB0"

    def _connect(self):
        if self.paused:
            self.state["serialConnected"] = False
            self.state["serialPaused"] = True
            return False

        self.port_path = self._find_port()
        self.state["port"] = self.port_path
        if not os.path.exists(self.port_path):
            self.state["serialConnected"] = False
            return False

        try:
            fd = os.open(self.port_path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            attrs = termios.tcgetattr(fd)
            attrs[4] = attrs[5] = termios.B9600
            attrs[2] = (attrs[2] & ~termios.CSIZE) | termios.CS8 | termios.CLOCAL | termios.CREAD
            attrs[2] &= ~(termios.PARENB | termios.CSTOPB | termios.HUPCL)
            attrs[3] = 0
            attrs[0] = 0
            attrs[1] = 0
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            self.fd = fd
            self.rx_buffer = ""
            self.state["serialConnected"] = True
            self.state["serialPaused"] = False
            self.add_log(f"Arduino bağlantısı kuruldu ({self.port_path})", "success")
            return True
        except Exception:
            self.state["serialConnected"] = False
            self.fd = None
            return False

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception:
                pass
        self.fd = None
        self.state["serialConnected"] = False

    def set_paused(self, paused):
        with self.lock:
            self.paused = bool(paused)
            self.state["serialPaused"] = self.paused
            if self.paused:
                self.close()
                self.add_log("Seri port web panelinden serbest bırakıldı (Terminalden kullanılabilir).", "warn")
            else:
                self.add_log("Seri port bağlantısı yeniden etkinleştirildi.", "info")
                self._connect()

    def send_raw(self, cmd):
        with self.lock:
            if self.paused:
                return False
            if self.fd is None:
                if not self._connect():
                    return False
            try:
                os.write(self.fd, (cmd.strip() + "\n").encode("utf-8"))
                return True
            except Exception:
                self.close()
                return False

    def handle_card_scan(self, uid, card_type="MIFARE"):
        uid = uid.strip().upper()
        if not uid:
            return

        now = time.time()
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        card = store.get(uid)
        is_new = False

        if card is None:
            if self.auto_register:
                is_new = True
                card = store.upsert({
                    "uid": uid,
                    "name": f"Kart {uid[-5:]}",
                    "cardType": card_type,
                    "enabled": True,
                    "actionType": "none",
                    "actionParam": "",
                    "cooldownSec": 2.0,
                    "scanCount": 1,
                    "lastScannedAt": now_str,
                    "lastScannedTs": now
                })
                self.add_log(f"✨ Yeni kart algılandı ve otomatik kaydedildi: {uid} ({card_type})", "success", uid=uid)
            else:
                self.add_log(f"💳 Kayıtsız kart okundu: {uid} ({card_type}) — Kaydetmek için tıklayın.", "warn", uid=uid)
        else:
            card = store.upsert({
                "uid": uid,
                "cardType": card_type or card.get("cardType", "MIFARE"),
                "scanCount": int(card.get("scanCount", 0)) + 1,
                "lastScannedAt": now_str,
                "lastScannedTs": now
            })

        self.state["lastScan"] = {
            "uid": uid,
            "cardType": card_type,
            "time": time.strftime("%H:%M:%S"),
            "timestamp": int(now * 1000),
            "registered": card is not None,
            "isNew": is_new,
            "card": card
        }

        if card is not None and not is_new:
            if not card.get("enabled", True):
                self.add_log(f"⏸️ '{card['name']}' ({uid}) okundu fakat kart pasif durumda.", "warn", uid=uid)
                return

            cooldown = float(card.get("cooldownSec", 2.0))
            last_trig = self.last_trigger_by_uid.get(uid, 0.0)
            if now - last_trig < cooldown:
                return
            self.last_trigger_by_uid[uid] = now

            ok, msg = executor.execute(card)
            self.add_log(msg, "success" if ok else "error", uid=uid)

    def handle_inspect(self, data):
        uid = (data.get("uid") or "").strip().upper()
        sak = data.get("sak", "")
        chip_arch = data.get("chipArch", "")
        emv_hex = (data.get("emvHex") or "").strip()
        emv_ascii = (data.get("emvAscii") or "").strip()
        ats_hex = (data.get("atsHex") or "").strip()
        block0 = (data.get("block0") or "").strip()
        block4_hex = (data.get("block4Hex") or "").strip()
        block4_ascii = (data.get("block4Ascii") or "").strip()

        # EMV Hex içinden 50 (Application Label) ve 4F (AID) etiketlerini ayıkla
        emv_label = ""
        emv_aid = ""
        if emv_hex:
            raw_bytes = [int(x, 16) for x in emv_hex.split() if len(x) == 2]
            i = 0
            while i < len(raw_bytes) - 2:
                if raw_bytes[i] == 0x50:
                    ln = raw_bytes[i + 1]
                    if 0 < ln <= 20 and i + 2 + ln <= len(raw_bytes):
                        emv_label = "".join(chr(b) for b in raw_bytes[i + 2:i + 2 + ln] if 32 <= b <= 126)
                        break
                i += 1
            j = 0
            while j < len(raw_bytes) - 2:
                if raw_bytes[j] == 0x4F:
                    ln = raw_bytes[j + 1]
                    if 4 < ln <= 16 and j + 2 + ln <= len(raw_bytes):
                        emv_aid = "".join(f"{b:02X}" for b in raw_bytes[j + 2:j + 2 + ln])
                        break
                j += 1

        info = {
            "uid": uid,
            "sak": sak,
            "uidSize": data.get("uidSize", 4),
            "chipArch": chip_arch,
            "atsHex": ats_hex,
            "emvHex": emv_hex,
            "emvAscii": emv_ascii,
            "emvLabel": emv_label,
            "emvAid": emv_aid,
            "block0": block0,
            "block4Hex": block4_hex,
            "block4Ascii": block4_ascii
        }
        self.state["lastInspect"] = info
        summary_parts = [f"SAK={sak} ({chip_arch})"]
        if emv_label or emv_aid:
            summary_parts.append(f"EMV: {emv_label or 'Banka Kartı'} [AID: {emv_aid}]")
        elif ats_hex:
            summary_parts.append(f"ATS: {ats_hex}")
        if block0:
            summary_parts.append(f"Blok0: {block0[:23]}...")
        self.add_log(f"🔍 [{uid}] Derin Analiz -> " + " | ".join(summary_parts), "info", uid=uid)

    def _parse_line(self, line):
        line = line.strip()
        if not line:
            return

        start = line.find("{")
        end = line.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(line[start:end + 1])
                ev = data.get("event")
                if ev == "status":
                    self.state["version"] = data.get("version", "0x00")
                    self.state["antenna"] = data.get("antenna", "0x00")
                    self.state["rfidOk"] = bool(data.get("ok", False))
                    self.state["uptime"] = int(data.get("uptime", 0))
                    self.state["lastStatusTs"] = time.time()
                    return
                elif ev == "card":
                    uid = data.get("uid", "")
                    ctype = data.get("cardType", "MIFARE")
                    self.handle_card_scan(uid, ctype)
                    return
                elif ev == "inspect":
                    self.handle_inspect(data)
                    return
            except Exception:
                pass

        m = re.search(r"UID\s*:\s*([0-9A-Fa-f:\s]{4,})", line)
        if m and "RFID Okundu -> UID:" not in line:
            raw_uid = m.group(1).strip()
            parts = [p.zfill(2).upper() for p in re.split(r"[\s:]+", raw_uid) if p]
            if len(parts) >= 4:
                self.handle_card_scan(":".join(parts), "MIFARE")

    def _read_lines(self):
        if self.fd is None:
            return []
        try:
            while True:
                chunk = os.read(self.fd, 1024)
                if not chunk:
                    # USB kablosu çıkarılıp takıldığında EOF döner -> eski fd'yi kapat ki anında yeniden bağlansın!
                    self.close()
                    return []
                self.rx_buffer += chunk.decode("utf-8", errors="ignore")
        except BlockingIOError:
            pass
        except Exception:
            self.close()
            return []

        lines = []
        while "\n" in self.rx_buffer:
            line, self.rx_buffer = self.rx_buffer.split("\n", 1)
            line = line.strip()
            if line:
                lines.append(line)
        return lines

    def _worker(self):
        while self.running:
            if self.paused:
                time.sleep(0.5)
                continue
            if self.fd is None:
                if not self._connect():
                    time.sleep(1.0)
                    continue
            with self.lock:
                lines = self._read_lines()
            for line in lines:
                self._parse_line(line)
            time.sleep(0.15)


bridge = RfidSerialBridge()


class RfidHttpHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def log_message(self, format, *args):
        pass

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            payload = {
                "serialConnected": bridge.state["serialConnected"],
                "serialPaused": bridge.state["serialPaused"],
                "port": bridge.state["port"],
                "rfidOk": bridge.state["rfidOk"],
                "version": bridge.state["version"],
                "antenna": bridge.state["antenna"],
                "uptime": bridge.state["uptime"],
                "autoRegister": bridge.auto_register,
                "lastScan": bridge.state["lastScan"],
                "lastInspect": bridge.state.get("lastInspect"),
                "cards": store.get_all(),
                "logs": bridge.state["logs"],
                "presets": ACTION_PRESETS
            }
            self._send_json(payload)
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        data = self._read_json()

        if parsed.path == "/api/cards/save":
            uid = (data.get("uid") or "").strip().upper()
            if not uid:
                self._send_json({"ok": False, "error": "UID boş olamaz!"}, 400)
                return
            saved = store.upsert(data)
            bridge.add_log(
                f"💾 '{saved['name']}' ({saved['uid']}) kaydedildi -> Fonksiyon: {saved['actionType']}",
                "success",
                uid=saved["uid"]
            )
            if bridge.state["lastScan"] and bridge.state["lastScan"].get("uid") == saved["uid"]:
                bridge.state["lastScan"]["registered"] = True
                bridge.state["lastScan"]["card"] = saved
            self._send_json({"ok": True, "card": saved})
            return

        elif parsed.path == "/api/cards/delete":
            uid = (data.get("uid") or "").strip().upper()
            deleted = store.delete(uid)
            if deleted:
                bridge.add_log(f"🗑️ Kart silindi: {uid}", "warn", uid=uid)
            self._send_json({"ok": deleted})
            return

        elif parsed.path == "/api/cards/test-action":
            uid = (data.get("uid") or "").strip().upper()
            card = store.get(uid) if uid else None
            temp_card = {
                "uid": uid or "TEST-UID",
                "name": data.get("name") or (card["name"] if card else "Test Kartı"),
                "actionType": data.get("actionType") or (card["actionType"] if card else "none"),
                "actionParam": data.get("actionParam") if "actionParam" in data else (card["actionParam"] if card else "")
            }
            ok, msg = executor.execute(temp_card)
            bridge.add_log(f"🧪 [TEST] {msg}", "success" if ok else "error", uid=temp_card["uid"])
            self._send_json({"ok": ok, "message": msg})
            return

        elif parsed.path == "/api/simulate-scan":
            uid = (data.get("uid") or "").strip().upper()
            if not uid:
                import random
                uid = ":".join(f"{random.randint(16, 254):02X}" for _ in range(4))
            card_type = data.get("cardType") or "MIFARE 1KB (Simülasyon)"
            bridge.handle_card_scan(uid, card_type)
            self._send_json({"ok": True, "uid": uid})
            return

        elif parsed.path == "/api/settings":
            if "autoRegister" in data:
                bridge.auto_register = bool(data["autoRegister"])
                durum = "AÇIK" if bridge.auto_register else "KAPALI"
                bridge.add_log(f"⚙️ Okununca Otomatik Kaydetme: {durum}", "info")
            if "serialPaused" in data:
                bridge.set_paused(bool(data["serialPaused"]))
            if data.get("rfidReset"):
                sent = bridge.send_raw("INIT")
                bridge.add_log("🔄 RC522 yeniden başlatma komutu gönderildi.", "info" if sent else "warn")
            self._send_json({"ok": True, "autoRegister": bridge.auto_register, "serialPaused": bridge.paused})
            return

        self._send_json({"ok": False, "error": "Bilinmeyen endpoint"}, 404)


class ThreadedHTTPServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    os.makedirs(WEB_DIR, exist_ok=True)
    server = ThreadedHTTPServer(("0.0.0.0", HTTP_PORT), RfidHttpHandler)
    print(f"RFID Otomasyon Web Paneli calisiyor: http://localhost:{HTTP_PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        bridge.close()
