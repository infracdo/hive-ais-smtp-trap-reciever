#!/usr/bin/env python3
"""
Test ONT Registration Decoder
"""

# Inline decoder for testing (same as in snmp_trap_receiver.py)
class ONTRegistrationDecoder:
    """Decoder for ONT registration trap data"""
    
    @staticmethod
    def decode_serial_number(hex_value: str) -> dict:
        """Decode ONT serial number from hex"""
        try:
            # Remove '0x' prefix if present
            hex_clean = hex_value.replace('0x', '')
            
            # First 4 bytes are vendor ID (ASCII)
            vendor_bytes = bytes.fromhex(hex_clean[:8])
            vendor_id = vendor_bytes.decode('ascii', errors='ignore')
            
            # Rest is device serial
            device_serial = hex_clean[8:].upper()
            
            return {
                'vendor_id': vendor_id,
                'device_serial': device_serial,
                'full_serial': f"{vendor_id}{device_serial}"
            }
        except Exception as e:
            return {'full_serial': hex_value}
    
    @staticmethod
    def decode_olt_port(ont_index: str) -> str:
        """
        Decode OLT port from ONT index
        
        ONT index format: 285278465 (encoded as 4 bytes)
        Encoding: [rack/frame, slot, subslot, port]
        Example: 285278465 = 0x11010101 = [17, 1, 1, 1]
        Display: gpon-olt_slot/subslot/port (skip rack/frame)
        """
        try:
            index = int(ont_index)
            bytes_val = index.to_bytes(4, 'big')
            slot = bytes_val[1]
            subslot = bytes_val[2]
            port = bytes_val[3]
            return f"gpon-olt_{slot}/{subslot}/{port}"
        except Exception:
            return "Unknown"
    
    @staticmethod
    def decode_timestamp(hex_value: str) -> str:
        """Decode SNMP DateAndTime from hex"""
        try:
            hex_clean = hex_value.replace('0x', '')
            
            # SNMP DateAndTime format: year(2), month, day, hour, min, sec, decisec
            year = int(hex_clean[0:4], 16)
            month = int(hex_clean[4:6], 16)
            day = int(hex_clean[6:8], 16)
            hour = int(hex_clean[8:10], 16)
            minute = int(hex_clean[10:12], 16)
            second = int(hex_clean[12:14], 16)
            
            return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
        except Exception as e:
            return hex_value
    
    @staticmethod
    def is_registration_trap(trap_oid: str) -> bool:
        """Check if this is an ONT registration trap"""
        # ZTE C320 ONT registration trap OID pattern
        return (trap_oid.startswith('1.3.6.1.4.1.3902.1082.500.10.3.1.80') or
                trap_oid.startswith('1.3.6.1.4.1.3902.1012.3.') and '.7.1' in trap_oid)
    
    @staticmethod
    def extract_registration_data(trap_data: dict) -> dict:
        """Extract ONT registration information from trap data"""
        registration_info = {
            'event_type': 'ont_registration',
            'ont_model': None,
            'ont_serial': None,
            'ont_firmware': None,
            'registration_time': None,
            'ont_index': None,
            'ont_password': None,
            'olt_port': None
        }
        
        for oid, data in trap_data.items():
            value = data.get('value', '')
            
            # ONT Model (OID pattern: *.20.2.1.2.1.15.*)
            if '.20.2.1.2.1.15.' in oid and isinstance(value, str) and not value.startswith('0x'):
                registration_info['ont_model'] = value
            
            # ONT Serial Number (OID pattern: *.10.2.2.5.1.2.*)
            elif '.10.2.2.5.1.2.' in oid and value.startswith('0x'):
                serial_decoded = ONTRegistrationDecoder.decode_serial_number(value)
                registration_info['ont_serial'] = serial_decoded.get('full_serial')
                registration_info['vendor_id'] = serial_decoded.get('vendor_id')
                registration_info['device_serial'] = serial_decoded.get('device_serial')
            
            # ONT Password (OID pattern: *.10.2.2.5.1.3.*)
            elif '.10.2.2.5.1.3.' in oid and value.startswith('0x'):
                registration_info['ont_password'] = value
            
            # ONT Firmware (OID pattern: *.10.2.2.5.1.8.*)
            elif '.10.2.2.5.1.8.' in oid and isinstance(value, str) and not value.startswith('0x'):
                registration_info['ont_firmware'] = value
            
            # Registration Timestamp (OID pattern: *.10.2.2.5.1.9.*)
            elif '.10.2.2.5.1.9.' in oid and value.startswith('0x'):
                registration_info['registration_time'] = ONTRegistrationDecoder.decode_timestamp(value)
            
            # Extract ONT index from OID (the large number before .0)
            if registration_info['ont_index'] is None:
                parts = oid.split('.')
                for i, part in enumerate(parts):
                    if len(part) > 6 and part.isdigit():
                        registration_info['ont_index'] = part
                        break
        
        # Decode OLT port from ONT index
        if registration_info['ont_index']:
            registration_info['olt_port'] = ONTRegistrationDecoder.decode_olt_port(registration_info['ont_index'])
        
        return registration_info

# Sample trap data from your real trap
sample_trap_data = {
    "1.3.6.1.2.1.1.3.0": {
        "oid": "1.3.6.1.2.1.1.3.0",
        "value": "102551400",
        "type": "TimeTicks"
    },
    "1.3.6.1.6.3.1.1.4.1.0": {
        "oid": "1.3.6.1.6.3.1.1.4.1.0",
        "value": "1.3.6.1.4.1.3902.1082.500.10.3.1.80",
        "type": "ObjectIdentifier",
        "is_trap_oid": True
    },
    "1.3.6.1.4.1.3902.1082.500.20.2.1.2.1.15.285278466.0": {
        "oid": "1.3.6.1.4.1.3902.1082.500.20.2.1.2.1.15.285278466.0",
        "value": "MH80",
        "type": "OctetString"
    },
    "1.3.6.1.4.1.3902.1082.500.10.2.2.5.1.2.285278466.0": {
        "oid": "1.3.6.1.4.1.3902.1082.500.10.2.2.5.1.2.285278466.0",
        "value": "0x4d48415208df4bd9",
        "type": "OctetString"
    },
    "1.3.6.1.4.1.3902.1082.500.10.2.2.5.1.3.285278466.0": {
        "oid": "1.3.6.1.4.1.3902.1082.500.10.2.2.5.1.3.285278466.0",
        "value": "0x00000000000000000000",
        "type": "OctetString"
    },
    "1.3.6.1.4.1.3902.1082.500.10.2.2.5.1.8.285278466.0": {
        "oid": "1.3.6.1.4.1.3902.1082.500.10.2.2.5.1.8.285278466.0",
        "value": "XPONV4.2.2M16",
        "type": "OctetString"
    },
    "1.3.6.1.4.1.3902.1082.500.10.2.2.5.1.9.285278466.0": {
        "oid": "1.3.6.1.4.1.3902.1082.500.10.2.2.5.1.9.285278466.0",
        "value": "0x07e90b030b071100000000",
        "type": "OctetString"
    }
}

print("="*80)
print("Testing ONT Registration Decoder")
print("="*80)

decoder = ONTRegistrationDecoder()

# Test trap OID detection
trap_oid = "1.3.6.1.4.1.3902.1082.500.10.3.1.80"
is_registration = decoder.is_registration_trap(trap_oid)
print(f"\n1. Trap OID Detection:")
print(f"   OID: {trap_oid}")
print(f"   Is Registration: {is_registration} {'✅' if is_registration else '❌'}")

# Test serial number decoding
print(f"\n2. Serial Number Decoding:")
serial_hex = "0x4d48415208df4bd9"
serial_decoded = decoder.decode_serial_number(serial_hex)
print(f"   Input: {serial_hex}")
print(f"   Vendor ID: {serial_decoded.get('vendor_id')}")
print(f"   Device Serial: {serial_decoded.get('device_serial')}")
print(f"   Full Serial: {serial_decoded.get('full_serial')}")

# Test timestamp decoding
print(f"\n3. Timestamp Decoding:")
timestamp_hex = "0x07e90b030b071100000000"
timestamp_decoded = decoder.decode_timestamp(timestamp_hex)
print(f"   Input: {timestamp_hex}")
print(f"   Decoded: {timestamp_decoded}")

# Test full registration data extraction
print(f"\n4. Full Registration Data Extraction:")
registration_data = decoder.extract_registration_data(sample_trap_data)
print(f"   Event Type: {registration_data['event_type']}")
print(f"   ONT Model: {registration_data['ont_model']}")
print(f"   ONT Serial: {registration_data['ont_serial']}")
print(f"   Vendor ID: {registration_data.get('vendor_id')}")
print(f"   Device Serial: {registration_data.get('device_serial')}")
print(f"   ONT Firmware: {registration_data['ont_firmware']}")
print(f"   Registration Time: {registration_data['registration_time']}")
print(f"   ONT Index: {registration_data['ont_index']}")
print(f"   ONT Password: {registration_data['ont_password']}")

# Show what would be sent to Kafka
print(f"\n5. Kafka Message Preview:")
print("="*80)
import json
kafka_message = {
    'timestamp': '2025-11-03T03:07:18.805037Z',
    'source_ip': '10.42.3.24',
    'event_type': 'ont_registration',
    'ont_data': registration_data,
    'trap_oid': trap_oid
}
print(json.dumps(kafka_message, indent=2))

print("\n" + "="*80)
print("✅ Decoder Test Complete!")
print("="*80)
