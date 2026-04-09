import usb_hid

# HIDShell boot.py — Pico W CP10.1.4
# Keyboard (for LED response channel) + Vendor HID (for command channel)
# Report ID 4, usage_page=0xFF, 63-byte reports

COMMAND_HID = usb_hid.Device(
    report_descriptor=bytes((
        0x06, 0x00, 0xFF,  # Usage Page (Vendor Defined 0xFF00)
        0x09, 0x01,        # Usage (Vendor Usage 1)
        0xA1, 0x01,        # Collection (Application)
        0x85, 0x04,        # Report ID 4

        # IN report: Pico → Host (commands to listener)
        0x09, 0x02,
        0x15, 0x00,
        0x26, 0xFF, 0x00,
        0x75, 0x08,
        0x95, 0x3F,        # 63 bytes
        0x81, 0x02,        # Input

        # OUT report: Host → Pico (placeholder, not used by CP10)
        0x09, 0x03,
        0x15, 0x00,
        0x26, 0xFF, 0x00,
        0x75, 0x08,
        0x95, 0x3F,        # 63 bytes
        0x91, 0x02,        # Output

        0xC0,
    )),
    usage_page=0xFF,
    usage=0x01,
    report_ids=(4,),
    in_report_lengths=(63,),
    out_report_lengths=(63,),
)

usb_hid.enable((
    usb_hid.Device.KEYBOARD,
    COMMAND_HID,
))
