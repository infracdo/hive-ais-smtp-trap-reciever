#!/usr/bin/env python3
"""
Decode NMS Hello / Interface Status Trap
"""

import json

trap_data = {
    "timestamp": "2025-11-03T03:38:26.879087Z",
    "source_ip": "10.42.3.24",
    "source_port": 161,
    "trap_oid": "1.3.6.1.4.1.3902.1082.30.20.3.4",
    "trap_data": {
        "1.3.6.1.2.1.1.3.0": {
            "value": "102738300",
            "type": "TimeTicks"
        },
        "1.3.6.1.2.1.2.2.1.7.285278467": {
            "value": "1",
            "type": "Integer"
        },
        "1.3.6.1.2.1.2.2.1.8.285278467": {
            "value": "2",
            "type": "Integer"
        },
        "1.3.6.1.2.1.2.2.1.3.285278467": {
            "value": "250",
            "type": "Integer"
        }
    }
}

print("="*80)
print("ZTE C320 SNMP Trap Analysis - NMS Hello / Interface Status")
print("="*80)

print(f"\nTrap Received: {trap_data['timestamp']}")
print(f"Source: {trap_data['source_ip']}")
print(f"Trap OID: {trap_data['trap_oid']}")

print("\n" + "="*80)
print("TRAP TYPE ANALYSIS")
print("="*80)

trap_oid = trap_data['trap_oid']
print(f"\nTrap OID Breakdown:")
print(f"  1.3.6.1.4.1           = iso.org.dod.internet.private.enterprises")
print(f"  3902                  = ZTE Corporation")
print(f"  1082                  = C320 Platform")
print(f"  30                    = Management/NMS branch")
print(f"  20                    = Event/Status notifications")
print(f"  3                     = Sub-category")
print(f"  4                     = Notification type")

print(f"\n🔍 TRAP TYPE: NMS Hello / Keepalive or Interface Status Event")
print(f"   This appears to be a periodic heartbeat/status trap")

print("\n" + "="*80)
print("STANDARD MIB-II OIDS DETECTED")
print("="*80)

# Decode standard MIB-II interface table OIDs
# 1.3.6.1.2.1.2.2.1 = ifTable (interfaces table)
# .7 = ifAdminStatus
# .8 = ifOperStatus  
# .3 = ifType

interface_index = "285278467"

print(f"\nInterface Index: {interface_index}")
print(f"(This is likely a PON port or ONT interface)")

# ifAdminStatus (1.3.6.1.2.1.2.2.1.7)
admin_status = trap_data['trap_data']['1.3.6.1.2.1.2.2.1.7.285278467']['value']
admin_status_map = {
    "1": "up(1) - Interface is administratively up",
    "2": "down(2) - Interface is administratively down",
    "3": "testing(3) - Interface is in testing mode"
}
print(f"\n1. ifAdminStatus (OID: 1.3.6.1.2.1.2.2.1.7.{interface_index})")
print(f"   Value: {admin_status}")
print(f"   Meaning: {admin_status_map.get(admin_status, 'Unknown')}")

# ifOperStatus (1.3.6.1.2.1.2.2.1.8)
oper_status = trap_data['trap_data']['1.3.6.1.2.1.2.2.1.8.285278467']['value']
oper_status_map = {
    "1": "up(1) - Interface is operationally up and ready",
    "2": "down(2) - Interface is operationally down",
    "3": "testing(3) - Interface is in testing mode",
    "4": "unknown(4) - Status cannot be determined",
    "5": "dormant(5) - Interface is waiting for external actions",
    "6": "notPresent(6) - Component not present",
    "7": "lowerLayerDown(7) - Lower layer interface is down"
}
print(f"\n2. ifOperStatus (OID: 1.3.6.1.2.1.2.2.1.8.{interface_index})")
print(f"   Value: {oper_status}")
print(f"   Meaning: {oper_status_map.get(oper_status, 'Unknown')}")

# ifType (1.3.6.1.2.1.2.2.1.3)
if_type = trap_data['trap_data']['1.3.6.1.2.1.2.2.1.3.285278467']['value']
if_type_map = {
    "6": "ethernetCsmacd(6) - Ethernet interface",
    "24": "softwareLoopback(24) - Software loopback",
    "250": "gpon(250) - GPON interface (vendor-specific)",
    "251": "epon(251) - EPON interface (vendor-specific)"
}
print(f"\n3. ifType (OID: 1.3.6.1.2.1.2.2.1.3.{interface_index})")
print(f"   Value: {if_type}")
print(f"   Meaning: {if_type_map.get(if_type, f'Type {if_type} - Vendor specific or uncommon type')}")

# sysUpTime
uptime_ticks = int(trap_data['trap_data']['1.3.6.1.2.1.1.3.0']['value'])
uptime_seconds = uptime_ticks / 100
uptime_days = int(uptime_seconds // 86400)
uptime_hours = int((uptime_seconds % 86400) // 3600)
uptime_minutes = int((uptime_seconds % 3600) // 60)
uptime_secs = int(uptime_seconds % 60)

print(f"\n4. sysUpTime (OID: 1.3.6.1.2.1.1.3.0)")
print(f"   Value: {uptime_ticks} ticks")
print(f"   Uptime: {uptime_days} days, {uptime_hours:02d}:{uptime_minutes:02d}:{uptime_secs:02d}")

print("\n" + "="*80)
print("INTERPRETATION")
print("="*80)

status_emoji = "🟢" if admin_status == "1" and oper_status == "1" else "🔴" if oper_status == "2" else "🟡"

print(f"\n{status_emoji} Interface Status Summary:")
print(f"   Interface ID: {interface_index}")
print(f"   Type: GPON interface (type 250)")
print(f"   Admin Status: {'UP' if admin_status == '1' else 'DOWN'}")
print(f"   Operational Status: {oper_status_map.get(oper_status, 'Unknown').split('-')[0].strip()}")
print(f"   System Uptime: {uptime_days} days, {uptime_hours:02d}:{uptime_minutes:02d}:{uptime_secs:02d}")

if admin_status == "1" and oper_status == "2":
    print(f"\n   ⚠️  Note: Interface is administratively UP but operationally DOWN")
    print(f"   This typically means:")
    print(f"   - Physical link is down (no light/signal)")
    print(f"   - ONT disconnected or powered off")
    print(f"   - Fiber cut or damaged")
elif admin_status == "1" and oper_status == "1":
    print(f"\n   ✅ Interface is fully operational")

print("\n" + "="*80)
print("TRAP PURPOSE")
print("="*80)

print(f"""
📡 NMS Hello / Keepalive Trap

This trap serves multiple purposes:

1. **Heartbeat/Keepalive:**
   - Sent every 120 seconds (as you mentioned)
   - Confirms OLT is alive and responsive
   - Allows NMS to detect OLT failures

2. **Interface Status Monitoring:**
   - Reports current status of PON interfaces
   - Monitors GPON port operational state
   - Tracks interface up/down events

3. **System Health Check:**
   - Includes system uptime
   - Provides interface statistics
   - Enables proactive monitoring

📊 Recommended Actions:

1. **Track in Database:**
   - Store interface status changes
   - Monitor uptime trends
   - Alert on unexpected down events

2. **Filter for Changes:**
   - Only log when status changes (not every 120s)
   - Reduce log volume while keeping important events

3. **Dashboard Integration:**
   - Show OLT uptime
   - Display interface status
   - Create availability metrics
""")

print("="*80)
print("KAFKA MESSAGE STRUCTURE")
print("="*80)

decoded_message = {
    "timestamp": trap_data['timestamp'],
    "source_ip": trap_data['source_ip'],
    "event_type": "nms_hello",
    "trap_oid": trap_data['trap_oid'],
    "system": {
        "uptime_ticks": uptime_ticks,
        "uptime_seconds": int(uptime_seconds),
        "uptime_formatted": f"{uptime_days}d {uptime_hours:02d}:{uptime_minutes:02d}:{uptime_secs:02d}"
    },
    "interface": {
        "index": interface_index,
        "type": int(if_type),
        "type_name": if_type_map.get(if_type, "Unknown"),
        "admin_status": int(admin_status),
        "admin_status_name": "up" if admin_status == "1" else "down",
        "oper_status": int(oper_status),
        "oper_status_name": oper_status_map.get(oper_status, "Unknown").split('-')[0].strip().lower(),
        "is_operational": admin_status == "1" and oper_status == "1"
    }
}

print("\nProposed Kafka message structure:")
print(json.dumps(decoded_message, indent=2))

print("\n" + "="*80)
