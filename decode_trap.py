#!/usr/bin/env python3
"""
Trap Decoder - Analyze the specific trap received
"""

import binascii
from datetime import datetime

# The trap data received
trap_data = {
    "timestamp": "2025-11-03T03:07:18.805037Z",
    "source_ip": "10.42.3.24",
    "trap_oid": "1.3.6.1.4.1.3902.1082.500.10.3.1.80",
    "variables": {
        "1.3.6.1.2.1.1.3.0": {
            "value": "102551400",
            "type": "TimeTicks",
            "meaning": "sysUpTime - System has been up for 102551400 ticks (11 days, 20:45:14)"
        },
        "1.3.6.1.4.1.3902.1082.500.20.2.1.2.1.15.285278466.0": {
            "value": "MH80",
            "type": "OctetString",
            "possible_meaning": "ONT Model/Type: MH80 (ZTE device model)"
        },
        "1.3.6.1.4.1.3902.1082.500.10.2.2.5.1.2.285278466.0": {
            "value": "0x4d48415208df4bd9",
            "type": "OctetString",
            "decoded": None,
            "possible_meaning": "ONT Serial Number"
        },
        "1.3.6.1.4.1.3902.1082.500.10.2.2.5.1.3.285278466.0": {
            "value": "0x00000000000000000000",
            "type": "OctetString",
            "decoded": "All zeros - possibly password or authentication field",
            "possible_meaning": "ONT Password/Authentication"
        },
        "1.3.6.1.4.1.3902.1082.500.10.2.2.5.1.8.285278466.0": {
            "value": "XPONV4.2.2M16",
            "type": "OctetString",
            "possible_meaning": "ONT Firmware Version: XPONV4.2.2M16"
        },
        "1.3.6.1.4.1.3902.1082.500.10.2.2.5.1.9.285278466.0": {
            "value": "0x07e90b030b071100000000",
            "type": "OctetString",
            "decoded": None,
            "possible_meaning": "Timestamp or Date field"
        }
    }
}

print("="*80)
print("ZTE C320 SNMP Trap Analysis")
print("="*80)

print(f"\nTrap Received: {trap_data['timestamp']}")
print(f"Source: {trap_data['source_ip']}")
print(f"Trap OID: {trap_data['trap_oid']}")

print("\n" + "="*80)
print("TRAP TYPE ANALYSIS")
print("="*80)

# Analyze trap OID structure
trap_oid = trap_data['trap_oid']
print(f"\nTrap OID Breakdown:")
print(f"  1.3.6.1.4.1           = iso.org.dod.internet.private.enterprises")
print(f"  3902                  = ZTE Corporation (ZTE Enterprise MIB)")
print(f"  1082                  = Unknown branch (not in standard ZTE PON MIBs)")
print(f"  500                   = Possible: Service/Event branch")
print(f"  10                    = Possible: GPON/PON related")
print(f"  3                     = Sub-category")
print(f"  1                     = Table/Object")
print(f"  80                    = Notification/Trap number")

print(f"\n🔍 LIKELY TRAP TYPE: ONT Registration/Discovery Event")
print(f"   (Based on the data containing ONT model, serial, firmware)")

print("\n" + "="*80)
print("VARIABLE BINDINGS ANALYSIS")
print("="*80)

# Decode serial number
serial_hex = "4d48415208df4bd9"
try:
    # First 4 bytes are usually vendor code in ASCII
    vendor_part = bytes.fromhex(serial_hex[:8]).decode('ascii')
    # Rest is device serial
    device_part = serial_hex[8:]
    print(f"\n1. ONT Serial Number:")
    print(f"   Hex: 0x{serial_hex}")
    print(f"   Vendor ID: {vendor_part} (ASCII)")
    print(f"   Device Serial: {device_part}")
    print(f"   Full Serial: {vendor_part}{device_part}")
except:
    print(f"\n1. ONT Serial Number: 0x{serial_hex}")

# Decode timestamp
timestamp_hex = "07e90b030b071100000000"
try:
    # Typical SNMP DateAndTime format: year(2), month, day, hour, min, sec, decisec, etc
    year = int(timestamp_hex[0:4], 16)
    month = int(timestamp_hex[4:6], 16)
    day = int(timestamp_hex[6:8], 16)
    hour = int(timestamp_hex[8:10], 16)
    minute = int(timestamp_hex[10:12], 16)
    second = int(timestamp_hex[12:14], 16)
    
    print(f"\n2. Timestamp Field:")
    print(f"   Hex: 0x{timestamp_hex}")
    print(f"   Decoded Date: {year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")
    print(f"   Meaning: Likely ONT registration time or last boot time")
except:
    print(f"\n2. Timestamp Field: 0x{timestamp_hex}")

print(f"\n3. ONT Model: MH80")
print(f"   Manufacturer: ZTE")
print(f"   Type: GPON ONT/ONU")

print(f"\n4. ONT Firmware: XPONV4.2.2M16")
print(f"   Version: V4.2.2")
print(f"   Build: M16")

print(f"\n5. ONT Password/Auth: 0x00000000000000000000")
print(f"   Status: All zeros (empty/default)")

# Analyze the common index
index = "285278466"
print(f"\n6. Common Index: {index}")
print(f"   Appears in all ONU-specific OIDs")
print(f"   Likely: Internal ONU identifier or interface index")

print("\n" + "="*80)
print("CONCLUSION")
print("="*80)

print(f"""
🎯 TRAP SUMMARY:
   Type: ONT/ONU Registration or Discovery Event
   Device: ZTE MH80 GPON ONT
   Serial: MHAR{serial_hex[8:].upper()} (approximate)
   Firmware: XPONV4.2.2M16
   Status: Device registered to OLT at 10.42.3.24
   
📝 NOTES:
   - This trap indicates an ONT has come online or re-registered
   - The OID structure (1.3.6.1.4.1.3902.1082.500.*) is not in standard
     ZTE PON MIBs, suggesting it may be from a proprietary/custom MIB
   - The index 285278466 appears to be a unique identifier for this ONT
   - All parameters relate to ONT identification and status

🔧 RECOMMENDATION:
   - Request the complete MIB file for OID 1.3.6.1.4.1.3902.1082.500
     from ZTE or check for updated C320 firmware documentation
   - This appears to be a newer/different MIB tree than the ZXGPON-* MIBs
   - The trap provides valuable ONT inventory data (model, serial, firmware)
""")

print("="*80)
