<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows-blue?style=flat-square&logo=windows" />
  <img src="https://img.shields.io/badge/device-Raspberry%20Pi%20Pico%20W-purple?style=flat-square&logo=raspberrypi" />
  <img src="https://img.shields.io/badge/lang-CircuitPython%20%7C%20Python-green?style=flat-square&logo=python" />
  <img src="https://img.shields.io/badge/license-MIT-red?style=flat-square" />
</p>

<p align="center">
  <pre align="center">
  _   _ ___ ____  ____  _          _ _ 
 | | | |_ _|  _ \/ ___|| |__   ___| | |
 | |_| || || | | \___ \| '_ \ / _ \ | |
 |  _  || || |_| |___) | | | |  __/ | |
 |_| |_|___|____/|____/|_| |_|\___|_|_|
  </pre>
</p>

<h3 align="center">Covert HID Reverse Shell</h3>

<p align="center">
  <i>A bidirectional covert channel that turns a USB keyboard device into a reverse shell<br>using LED state changes and vendor HID reports as the transport layer.</i>
</p>

<p align="center">
  <b>No network &nbsp;·&nbsp; No drivers &nbsp;·&nbsp; No detection</b>
</p>

<p align="center">
  <a href="https://youtube.com/@0dayscyber"><b>Watch Demo</b></a> &nbsp;·&nbsp;
  <a href="#-quick-start"><b>Quick Start</b></a> &nbsp;·&nbsp;
  <a href="#-how-it-works"><b>How It Works</b></a> &nbsp;·&nbsp;
  <a href="#-wifi-mode"><b>WiFi Mode</b></a>
</p>

---

## What is this?

HIDShell is an open-source covert reverse shell that communicates entirely over USB HID — the same protocol your keyboard uses. It's invisible to EDR, network monitors, and DLP because USB HID traffic is architecturally below the layer those tools inspect.

**The victim machine sees a keyboard. Nothing more.**

Commands flow in through a vendor-defined HID interface. The agent executes them and sends output back by toggling keyboard LEDs — NumLock, CapsLock, ScrollLock — which the device decodes back into text. No TCP. No DNS. No files on disk.

```
┌──────────┐         USB HID          ┌──────────────┐
│  VICTIM  │◄════════════════════════►│   PICO W      │
│          │  Keyboard + Vendor HID   │               │
│ implant  │                          │  code.py      │
│   .py    │  ── Cmds (HID IN) ─────►│               │
│          │  ◄── Output (LEDs) ──────│  WiFi AP ─────┼──► Attacker
└──────────┘                          └──────────────┘    (browser)
```

> **⚠️ Legal Notice:** This tool is for authorized penetration testing and red team engagements only. Unauthorized access to computer systems is illegal. Always obtain written authorization before use.

---

## Why?

| Problem | HIDShell's Answer |
|---------|-------------------|
| Network C2 triggers IDS/NDR | **No network traffic at all** |
| EDR monitors process behaviour | **HID reports bypass userspace hooks** |
| DLP watches file writes | **Agent runs from memory** |
| USB device policies block storage | **HID class is always trusted** |
| Physical access tools are closed-source | **Fully open, audit everything** |

Existing tools like [Diabolic Shell](https://www.crowdsupply.com/unit-72784/diabolic-parasite) are closed-source and hardware-locked plus over $100 USD to purchase, HIDShell achieves the same covert C2 with a **$6 Raspberry Pi Pico W** and open-source CircuitPython.

---

## 📡 Two Covert Channels

| Channel | Direction | Transport | Speed |
|---------|-----------|-----------|-------|
| **Commands** | Attacker → Victim | Vendor HID Reports (64 byte) | ~1 KB/s |
| **Responses** | Victim → Attacker | Keyboard LED Toggles | ~6 bytes/s |

### LED Encoding Protocol

Each byte is transmitted MSB-first via LED state changes:

```
NumLock toggle   = bit 1
CapsLock toggle  = bit 0
ScrollLock toggle = commit byte (after 8 bits)

Framing:
  [STX 0x02] [data bytes...] [ETX 0x03]
```

**Example:** Transmitting `A` (0x41 = `01000001`)

```
Caps→0  Num→1  Caps→0  Caps→0  Caps→0  Caps→0  Caps→0  Num→1  Scroll→commit
```

9 toggles × 30ms = ~270ms per byte. A 50-byte WiFi password exfiltrates in ~14 seconds.

---

## 🚀 Quick Start

### Hardware

| Item | Price | Notes |
|------|-------|-------|
| **Raspberry Pi Pico W** | ~$6 | WiFi mode (recommended) |
| **Raspberry Pi Pico** | ~$4 | Wired mode (dev/testing) |
| Micro-USB cable | — | You already have one |

That's it. No adapters, no custom PCBs, no soldering.

### Step 1 — Flash CircuitPython

> **Pico W** → CircuitPython **9.x** (has WiFi modules)
> **Pico** → CircuitPython **7.x+**

1. Hold **BOOTSEL** while plugging in the Pico
2. It mounts as `RPI-RP2`
3. Download the `.uf2` from [circuitpython.org](https://circuitpython.org/board/raspberry_pi_pico_w/)
4. Drag the `.uf2` onto the drive
5. It reboots and mounts as `CIRCUITPY`

### Step 2 — Deploy Device Code

Copy these files to the root of `CIRCUITPY`:

```
CIRCUITPY/
├── boot.py          ← USB HID descriptor config
└── code.py          ← Use code.py (wired) or code_wifi.py (WiFi)
```

> **Important:** Power-cycle the Pico after copying `boot.py` — unplug the USB cable and plug it back in. USB descriptors only register at cold boot, not on soft reset.

### Step 3 — Verify HID Interfaces

Open **Device Manager** on Windows → **Human Interface Devices**. You should see:

- ✅ `HID Keyboard Device` — the LED channel
- ✅ `HID-compliant vendor-defined device` — the command channel

If you only see the keyboard, `boot.py` didn't run. Check `boot_out.txt` on the `CIRCUITPY` drive for errors.

### Step 4 — Install Agent Dependencies

```powershell
pip install hidapi
```

### Step 5 — Test Locally

**Option A — Split-view testing (recommended):**

```powershell
# Terminal 1: Run the test harness FIRST
python test_harness.py

# Then open Thonny to see decoded output on the Pico
```

The test harness simulates the implant side (sends commands via HID, executes locally, sends output via LEDs). Thonny shows the Pico's decoded view of both channels.

**Option B — Full implant testing:**

```powershell
# Find your Pico's VID/PID
python -c "import hid;[print('VID=0x%04X PID=0x%04X %s'%(d['vendor_id'],d['product_id'],d.get('product_string','?'))) for d in hid.enumerate() if d['usage_page']==0xFF00 or d['usage_page']==0xFF]"

# Update VENDOR_ID/PRODUCT_ID in implant.py if needed, then run:
python implant.py
```

### Step 6 — Send Your First Command

At the `hidshell >` prompt in the test harness:

```
hidshell > ping
hidshell > whoami
hidshell > netsh wlan show profiles
```

Watch your keyboard LEDs flicker as data transmits back through the covert channel.

---

## 📶 WiFi Mode

WiFi mode replaces the wired attacker connection with a browser-based dashboard served from the Pico W's built-in WiFi radio.

### Setup

1. Flash **CircuitPython 9.x** for Pico W
2. Copy `boot.py` + `code_wifi.py` (rename to `code.py`) to `CIRCUITPY`
3. Power-cycle the Pico W
4. Connect to the WiFi AP from your attacker device:

```
SSID:     HIDShell
Password: h4ckth3pl4n3t
```

5. Open `http://192.168.4.1` in your browser

### Configuration

Edit the top of `code_wifi.py`:

```python
AP_SSID     = "HIDShell"          # Network name
AP_PASSWORD = "h4ckth3pl4n3t"     # Min 8 characters
AP_HIDDEN   = False               # True = hidden SSID
```

### WiFi Range

| Scenario | Range |
|----------|-------|
| Indoor, through walls | 15–25m |
| Indoor, line of sight | 30–50m |
| Outdoor, line of sight | 50–80m |

Range improves significantly with a high-gain adapter (Alfa AWUS036ACH etc.) on the attacker side. The bottleneck is the Pico W's small PCB trace antenna transmitting — your Alfa compensates on the receive side.

---

## Project Structure

```
hidshell/
│
├── boot.py              # USB HID descriptor configuration
│                        # Registers keyboard + vendor HID interfaces
│                        # Same file for both Pico and Pico W
│
├── code.py              # Pico decoder / C2 controller (wired mode)
│                        # Reads HID commands, decodes LED responses
│                        # Outputs to USB serial (Thonny)
│
├── code_wifi.py         # WiFi version (Pico W)
│                        # Runs AP + HTTP server + web dashboard
│                        # Replaces UART/serial entirely
│
├── implant.py           # Windows agent (runs on victim)
│                        # Reads vendor HID, executes commands
│                        # Sends output via LED toggles
│
├── test_harness.py      # Local testing tool
│                        # Simulates implant for dev/testing
│                        # Run first, then open Thonny
│
└── README.md            # You are here
```

---

## ⚙️ Configuration Reference

### boot.py

The boot configuration registers two HID interfaces with the host OS. No changes needed between Pico and Pico W.

**Key parameters:**

| Parameter | Value | Notes |
|-----------|-------|-------|
| `usage_page` | `0xFF` | Vendor-defined (CP 7.x truncates `0xFF00`) |
| `report_ids` | `(4,)` | Avoids collision with keyboard report ID 0 |
| `in_report_lengths` | `(63,)` | Max payload per HID report |
| `out_report_lengths` | `(63,)` | Matching OUT report size |

### implant.py

| Setting | Default | Description |
|---------|---------|-------------|
| `VENDOR_ID` | `0x239A` | Pico's USB vendor ID |
| `PRODUCT_ID` | `0x80F4` | Pico's USB product ID |
| `BIT_DELAY` | `0.02` | Seconds between LED toggles |
| `BYTE_DELAY` | `0.005` | Extra delay after byte commit |
| `MAX_OUTPUT` | `4096` | Max response bytes (bandwidth limit) |
| `CMD_TIMEOUT` | `30` | Command execution timeout (seconds) |

### Agent Built-in Commands

| Command | Response | Description |
|---------|----------|-------------|
| `__PING__` | `__PONG__` | Keepalive check |
| `__INFO__` | System info | Hostname, user, domain, arch, PID |
| `__EXIT__` | `__BYE__` | Agent self-terminates |

---

## 🔒 Engagement Hardening

For real red team deployments, apply these before going operational:

```python
# boot.py — hide the evidence
HIDE_DRIVE = True         # Remove CIRCUITPY from victim's file explorer
HIDE_USB_SERIAL = True    # Disable USB serial (no Thonny access)
```

```python
# code_wifi.py — stealth AP
AP_HIDDEN = True          # Hidden SSID (connect manually)
AP_SSID = "HP_Printer"    # Blend into the environment
```

```bash
# Compile agent — no Python dependency on victim
pyinstaller --onefile --noconsole --name RuntimeBroker implant.py
```

```python
# implant.py — match target's existing keyboard
VENDOR_ID  = 0x1532       # e.g. Razer
PRODUCT_ID = 0x02A2       # e.g. Ornata V3
```

---

## 🛡️ Why This Evades Detection

| Layer | Why it's blind |
|-------|----------------|
| **Network monitoring** | Zero TCP/DNS/HTTP from victim — WiFi AP is on the Pico |
| **EDR** | HID reports travel below the API layer EDR hooks |
| **DLP** | No files written to disk when agent runs from memory |
| **USB device policies** | HID keyboard class is universally trusted |
| **Process monitoring** | Hidden window, `CREATE_NO_WINDOW` child processes |
| **IPC detection** | No named pipes, shared memory, or COM objects |
| **Driver signing** | Standard HID class — OS built-in driver, no install |

---

## 🗺️ Roadmap

- [ ] **Error correction** — CRC per frame with retransmission
- [ ] **Compression** — zlib before LED transmission
- [ ] **Encryption** — AES-CTR with pre-shared key

---

## Contributing

Pull requests welcome. If you're building detection for this — even better. Open-source offensive tools make everyone's security stronger.

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/3bit-encoding`)
3. Commit changes (`git commit -m 'add 3-bit LED encoding'`)
4. Push (`git push origin feature/3bit-encoding`)
5. Open a Pull Request

---

## References

- [USB HID Specification](https://www.usb.org/hid) — LED indicator usage
- [CircuitPython USB HID docs](https://docs.circuitpython.org/en/latest/shared-bindings/usb_hid/)
- [Diabolic Parasite](https://www.crowdsupply.com/unit-72784/diabolic-parasite) — closed-source inspiration
- [HID Report Descriptors](https://eleccelerator.com/usbdescreqparser/) — descriptor parser tool

---

<p align="center">
  <b>Built for the offensive security community by <a href="https://youtube.com/@0dayscyber">0dayscyber</a></b><br>
  <sub>MIT License — use it, fork it, break it, improve it. Stay legal.</sub>
</p>
