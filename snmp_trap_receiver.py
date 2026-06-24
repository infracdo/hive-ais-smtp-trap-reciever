#!/usr/bin/env python3
"""
SNMP Trap Receiver to Kafka Publisher
Receives SNMP traps from ZTE C320 OLT and publishes to Kafka
"""

import os
import sys
import json
import logging
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

from pysnmp.entity import engine, config
from pysnmp.carrier.asyncore.dgram import udp
from pysnmp.entity.rfc3413 import ntfrcv
from pysnmp.proto.api import v2c
from pysnmp.hlapi import (
    getCmd, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity
)
from kafka import KafkaProducer
from kafka.errors import KafkaError

# Load environment variables
load_dotenv()

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NMSHelloDecoder:
    """Decoder for NMS Hello/Keepalive traps"""
    
    @staticmethod
    def is_nms_hello_trap(trap_oid: str) -> bool:
        """Check if this is an NMS hello/keepalive trap"""
        # ZTE C320 NMS hello trap OID pattern
        # 1.3.6.1.4.1.3902.1082.30.20.3.4
        return trap_oid and trap_oid.startswith('1.3.6.1.4.1.3902.1082.30.20')
    
    @staticmethod
    def extract_nms_hello_data(trap_data: dict) -> dict:
        """Extract NMS hello/interface status information from trap data"""
        hello_info = {
            'event_type': 'nms_hello',
            'system_uptime_ticks': None,
            'system_uptime_seconds': None,
            'system_uptime_formatted': None,
            'interface_index': None,
            'interface_type': None,
            'interface_type_name': None,
            'admin_status': None,
            'admin_status_name': None,
            'oper_status': None,
            'oper_status_name': None,
            'is_operational': False
        }
        
        # Status name mappings
        admin_status_map = {1: 'up', 2: 'down', 3: 'testing'}
        oper_status_map = {
            1: 'up', 2: 'down', 3: 'testing', 
            4: 'unknown', 5: 'dormant', 6: 'notPresent', 7: 'lowerLayerDown'
        }
        if_type_map = {
            6: 'ethernet', 24: 'loopback', 
            250: 'gpon', 251: 'epon'
        }
        
        interface_index = None
        
        for oid, data in trap_data.items():
            value = data.get('value', '')
            
            # System uptime (1.3.6.1.2.1.1.3.0)
            if oid == '1.3.6.1.2.1.1.3.0':
                try:
                    ticks = int(value)
                    seconds = ticks / 100
                    days = int(seconds // 86400)
                    hours = int((seconds % 86400) // 3600)
                    minutes = int((seconds % 3600) // 60)
                    secs = int(seconds % 60)
                    
                    hello_info['system_uptime_ticks'] = ticks
                    hello_info['system_uptime_seconds'] = int(seconds)
                    hello_info['system_uptime_formatted'] = f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
                except:
                    pass
            
            # Extract interface index from MIB-II ifTable OIDs
            # Pattern: 1.3.6.1.2.1.2.2.1.X.YYYYY where YYYYY is interface index
            if '.1.3.6.1.2.1.2.2.1.' in oid:
                parts = oid.split('.')
                if len(parts) >= 11:
                    interface_index = parts[10]
                    hello_info['interface_index'] = interface_index
                
                # ifAdminStatus (1.3.6.1.2.1.2.2.1.7)
                if '.1.3.6.1.2.1.2.2.1.7.' in oid:
                    try:
                        status = int(value)
                        hello_info['admin_status'] = status
                        hello_info['admin_status_name'] = admin_status_map.get(status, 'unknown')
                    except:
                        pass
                
                # ifOperStatus (1.3.6.1.2.1.2.2.1.8)
                elif '.1.3.6.1.2.1.2.2.1.8.' in oid:
                    try:
                        status = int(value)
                        hello_info['oper_status'] = status
                        hello_info['oper_status_name'] = oper_status_map.get(status, 'unknown')
                    except:
                        pass
                
                # ifType (1.3.6.1.2.1.2.2.1.3)
                elif '.1.3.6.1.2.1.2.2.1.3.' in oid:
                    try:
                        if_type = int(value)
                        hello_info['interface_type'] = if_type
                        hello_info['interface_type_name'] = if_type_map.get(if_type, f'type_{if_type}')
                    except:
                        pass
        
        # Determine if interface is operational
        hello_info['is_operational'] = (
            hello_info['admin_status'] == 1 and 
            hello_info['oper_status'] == 1
        )
        
        return hello_info


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
            logger.warning(f"Failed to decode serial number: {e}")
            return {'full_serial': hex_value}
    
    @staticmethod
    def decode_olt_port(ont_index: str) -> str:
        """
        Decode OLT port from ONT index
        
        ONT index format: 285278465 (encoded as 4 bytes)
        Encoding: [rack/frame, slot, subslot, port]
        Example: 285278465 = 0x11010101 = [17, 1, 1, 1]
        Display: gpon-olt_slot/subslot/port (skip rack/frame)
        
        Args:
            ont_index: ONT index string (e.g., "285278465")
        
        Returns:
            Formatted OLT port (e.g., "gpon-olt_1/1/1")
        """
        try:
            index = int(ont_index)
            
            # Convert to 4 bytes
            bytes_val = index.to_bytes(4, 'big')
            
            # Decode: bytes are [rack/frame, slot, subslot, port]
            # CLI shows slot/subslot/port only (skip rack/frame)
            rack_frame = bytes_val[0]
            slot = bytes_val[1]
            subslot = bytes_val[2]
            port = bytes_val[3]
            
            # Format as gpon-olt_slot/subslot/port
            return f"gpon-olt_{slot}/{subslot}/{port}"
        except Exception as e:
            logger.warning(f"Failed to decode OLT port from index '{ont_index}': {e}")
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
            logger.warning(f"Failed to decode timestamp: {e}")
            return hex_value
    
    @staticmethod
    def is_registration_trap(trap_oid: str) -> bool:
        """Check if this is an ONT registration trap"""
        # ZTE C320 ONT registration trap OID pattern
        # 1.3.6.1.4.1.3902.1082.500.10.3.1.80
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


class MIBLookup:
    """MIB database lookup helper"""
    
    def __init__(self, db_path: str = 'mib_database.db'):
        self.db_path = db_path
        self.conn = None
        self.enabled = False
        
        if Path(db_path).exists():
            try:
                self.conn = sqlite3.connect(db_path)
                self.conn.row_factory = sqlite3.Row
                self.enabled = True
                logger.info(f"MIB database loaded: {db_path}")
            except Exception as e:
                logger.warning(f"Failed to load MIB database: {e}")
        else:
            logger.warning(f"MIB database not found: {db_path}")
    
    def lookup_oid(self, oid: str) -> dict:
        """Look up OID and return information"""
        if not self.enabled:
            return {'oid': oid, 'name': oid}
        
        try:
            cursor = self.conn.cursor()
            
            # Try exact match
            cursor.execute('''
                SELECT name, oid, syntax, access, description, module
                FROM object_types WHERE oid = ?
            ''', (oid,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            
            # Try prefix match for table entries
            parts = oid.split('.')
            for i in range(len(parts), 0, -1):
                prefix = '.'.join(parts[:i])
                cursor.execute('''
                    SELECT name, oid, syntax, access, description, module
                    FROM object_types WHERE oid = ?
                ''', (prefix,))
                
                row = cursor.fetchone()
                if row:
                    result = dict(row)
                    result['index'] = '.'.join(parts[i:])
                    result['full_oid'] = oid
                    return result
            
            # No match found
            return {'oid': oid, 'name': oid}
            
        except Exception as e:
            logger.error(f"Error looking up OID {oid}: {e}")
            return {'oid': oid, 'name': oid}
    
    def lookup_notification(self, oid: str) -> dict:
        """Look up notification/trap by OID"""
        if not self.enabled:
            return None
        
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT name, oid, objects, description, module
                FROM notifications WHERE oid = ?
            ''', (oid,))
            
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error looking up notification {oid}: {e}")
            return None
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


class ManufacturerLookup:
    """Lookup manufacturer information from enterprise OIDs"""
    
    # IANA Enterprise Numbers - Common network equipment vendors
    ENTERPRISE_NUMBERS = {
        '9': 'Cisco Systems',
        '11': 'Hewlett Packard',
        '43': 'Sun Microsystems',
        '45': 'SynOptics',
        '171': 'D-Link Systems',
        '207': 'Allied Telesis',
        '232': 'Cabletron Systems',
        '311': 'Microsoft',
        '318': 'APC',
        '637': 'Alcatel-Lucent',
        '1588': 'ShoreTel',
        '1991': 'Foundry Networks',
        '2011': 'Huawei Technologies',
        '2021': 'Net-SNMP',
        '2636': 'Juniper Networks',
        '2863': 'Acme Packet',
        '3076': 'Alteon Networks',
        '3902': 'ZTE Corporation',
        '4526': 'Netgear',
        '4874': 'Avaya',
        '5624': 'Brocade',
        '6027': 'Force10 Networks',
        '6876': 'VMware',
        '8072': 'Net-SNMP',
        '9148': 'Arista Networks',
        '10002': 'Ubiquiti Networks',
        '12356': 'Fortinet',
        '14179': 'Riverbed Technology',
        '14823': 'Aruba Networks',
        '25506': 'H3C Technologies',
        '30065': 'Ruckus Wireless',
    }
    
    @staticmethod
    def parse_snmp_engine_id(engine_id: str) -> dict:
        """
        Parse SNMP Engine ID according to RFC 3411
        
        Format: [4 octets: format + enterprise] [variable: engine data]
        
        Args:
            engine_id: Hex string like "0x80000f3e03cc1afab31c1001" or "80000f3e03cc1afab31c1001"
        
        Returns:
            Dictionary with parsed components
        """
        result = {
            'raw': engine_id,
            'format': None,
            'enterprise_id': None,
            'enterprise_name': None,
            'engine_data': None,
            'parsed_data': None
        }
        
        try:
            # Clean hex string
            hex_str = engine_id.replace('0x', '').replace(':', '')
            
            if len(hex_str) < 10:  # Minimum 5 bytes
                return result
            
            # First byte is format (bit 7 always set to 1)
            format_byte = int(hex_str[0:2], 16)
            result['format'] = format_byte & 0x7F  # Remove leading 1 bit
            
            # Next 4 bytes are enterprise ID
            enterprise_bytes = hex_str[2:10]
            enterprise_id = int(enterprise_bytes, 16)
            result['enterprise_id'] = enterprise_id
            result['enterprise_name'] = ManufacturerLookup.ENTERPRISE_NUMBERS.get(
                str(enterprise_id), 
                f'Enterprise {enterprise_id}'
            )
            
            # Remaining bytes are engine-specific data
            engine_data = hex_str[10:]
            result['engine_data'] = engine_data
            
            # Parse based on format
            if result['format'] == 1:
                # Format 1: IPv4 address
                if len(engine_data) >= 8:
                    ip_bytes = [int(engine_data[i:i+2], 16) for i in range(0, 8, 2)]
                    result['parsed_data'] = f"{ip_bytes[0]}.{ip_bytes[1]}.{ip_bytes[2]}.{ip_bytes[3]}"
            elif result['format'] == 2:
                # Format 2: IPv6 address
                if len(engine_data) >= 32:
                    result['parsed_data'] = ':'.join([engine_data[i:i+4] for i in range(0, 32, 4)])
            elif result['format'] == 3:
                # Format 3: MAC address
                if len(engine_data) >= 12:
                    result['parsed_data'] = ':'.join([engine_data[i:i+2] for i in range(0, 12, 2)])
            elif result['format'] == 4:
                # Format 4: Text/administratively assigned
                try:
                    result['parsed_data'] = bytes.fromhex(engine_data).decode('ascii', errors='ignore')
                except:
                    result['parsed_data'] = engine_data
            elif result['format'] == 5:
                # Format 5: Octets (just show hex)
                result['parsed_data'] = engine_data
            
        except Exception as e:
            logger.warning(f"Failed to parse SNMP Engine ID: {e}")
        
        return result
    
    @staticmethod
    def get_manufacturer(oid: str) -> dict:
        """Extract manufacturer information from OID"""
        result = {
            'manufacturer': None,
            'enterprise_id': None,
            'is_enterprise': False,
            'is_standard': False
        }
        
        # Check if OID is in enterprise tree (1.3.6.1.4.1.X)
        if oid.startswith('1.3.6.1.4.1.'):
            result['is_enterprise'] = True
            parts = oid.split('.')
            if len(parts) > 6:
                enterprise_id = parts[6]
                result['enterprise_id'] = enterprise_id
                result['manufacturer'] = ManufacturerLookup.ENTERPRISE_NUMBERS.get(
                    enterprise_id, 
                    f'Enterprise {enterprise_id}'
                )
        # Check if OID is in standard MIB-2 tree (1.3.6.1.2.1.X)
        elif oid.startswith('1.3.6.1.2.1.'):
            result['is_standard'] = True
            result['manufacturer'] = 'IETF Standard MIB'
        # Check if OID is in experimental tree (1.3.6.1.3.X)
        elif oid.startswith('1.3.6.1.3.'):
            result['manufacturer'] = 'IETF Experimental'
        # Check if OID is in SNMPv2 tree (1.3.6.1.6.X)
        elif oid.startswith('1.3.6.1.6.'):
            result['manufacturer'] = 'SNMPv2'
        
        return result


class SNMPTrapToKafka:
    """SNMP Trap receiver that forwards traps to Kafka"""
    
    def __init__(self):
        self.snmp_engine = None
        self.kafka_producer = None
        self.mib_lookup = MIBLookup('mib_database.db')
        self.ont_decoder = ONTRegistrationDecoder()
        self.nms_decoder = NMSHelloDecoder()
        self.snmp_community = os.getenv('SNMP_COMMUNITY', 'devCommunity')
        self.snmp_timeout = float(os.getenv('SNMP_TIMEOUT', '2.0'))
        self.snmp_retries = int(os.getenv('SNMP_RETRIES', '1'))
        self.setup_kafka()
        self.setup_snmp()
    
    def setup_kafka(self):
        """Initialize Kafka producer"""
        kafka_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', '10.42.4.19:9092')
        
        try:
            self.kafka_producer = KafkaProducer(
                bootstrap_servers=kafka_servers.split(','),
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks=1,
                retries=3,
                max_in_flight_requests_per_connection=1
            )
            logger.info(f"Kafka producer initialized: {kafka_servers}")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            raise
    
    def setup_snmp(self):
        """Initialize SNMP trap receiver"""
        listen_host = os.getenv('SNMP_LISTEN_HOST', '0.0.0.0')
        listen_port = int(os.getenv('SNMP_LISTEN_PORT', '162'))
        community = os.getenv('SNMP_COMMUNITY', 'wg1Community')
        
        # Create SNMP engine
        self.snmp_engine = engine.SnmpEngine()
        
        # Configure transport endpoint
        config.addTransport(
            self.snmp_engine,
            udp.domainName,
            udp.UdpTransport().openServerMode((listen_host, listen_port))
        )
        
        # Configure community
        config.addV1System(self.snmp_engine, 'my-area', community)
        
        # Register trap callback
        ntfrcv.NotificationReceiver(self.snmp_engine, self.trap_callback)
        
        logger.info(f"SNMP trap receiver listening on {listen_host}:{listen_port}")
        logger.info(f"Community string: {community}")
    
    def parse_trap_data(self, var_binds):
        """Parse SNMP trap variable bindings with MIB lookups"""
        trap_data = {}
        trap_oid = None
        
        # System information from SNMPv2-MIB
        system_info = {
            'sysName': None,       # 1.3.6.1.2.1.1.5.0
            'sysLocation': None,   # 1.3.6.1.2.1.1.6.0
            'sysDescr': None,      # 1.3.6.1.2.1.1.1.0
            'sysObjectID': None,   # 1.3.6.1.2.1.1.2.0
            'sysContact': None,    # 1.3.6.1.2.1.1.4.0
            'sysUpTime': None      # 1.3.6.1.2.1.1.3.0
        }
        
        for oid, val in var_binds:
            print(f"Debug: OID={oid}, Data={val}")
            oid_str = str(oid)
            
            # Convert value to appropriate type
            if hasattr(val, 'prettyPrint'):
                value = val.prettyPrint()
            else:
                value = str(val)
            
            # Extract system information
            if oid_str == '1.3.6.1.2.1.1.5.0':
                system_info['sysName'] = value
            elif oid_str == '1.3.6.1.2.1.1.6.0':
                system_info['sysLocation'] = value
            elif oid_str == '1.3.6.1.2.1.1.1.0':
                system_info['sysDescr'] = value
            elif oid_str == '1.3.6.1.2.1.1.2.0':
                system_info['sysObjectID'] = value
            elif oid_str == '1.3.6.1.2.1.1.4.0':
                system_info['sysContact'] = value
            elif oid_str == '1.3.6.1.2.1.1.3.0':
                system_info['sysUpTime'] = value
            
            # Look up OID in MIB database
            mib_info = self.mib_lookup.lookup_oid(oid_str)
            
            # Get manufacturer info for this OID
            manufacturer_info = ManufacturerLookup.get_manufacturer(oid_str)
            
            # Build trap data entry
            entry = {
                'oid': oid_str,
                'value': value,
                'type': type(val).__name__,
                'manufacturer': manufacturer_info.get('manufacturer'),
                'is_enterprise': manufacturer_info.get('is_enterprise', False),
                'is_standard': manufacturer_info.get('is_standard', False)
            }
            
            # Add MIB information if found
            if 'name' in mib_info and mib_info['name'] != oid_str:
                entry['name'] = mib_info['name']
            
            if 'description' in mib_info:
                entry['description'] = mib_info['description'][:200]  # Truncate long descriptions
            
            if 'syntax' in mib_info:
                entry['syntax'] = mib_info['syntax']
            
            if 'index' in mib_info:
                entry['table_index'] = mib_info['index']
            
            # Check if this is the trap OID
            if oid_str.startswith('1.3.6.1.6.3.1.1.4.1'):
                trap_oid = value
                entry['is_trap_oid'] = True
            
            trap_data[oid_str] = entry
        
        # Look up trap notification info
        trap_info = None
        if trap_oid:
            trap_info = self.mib_lookup.lookup_notification(trap_oid)
        
        return trap_data, trap_info, system_info
    
    def query_device_hostname(self, device_ip: str, community: str = None) -> dict:
        """Query device for hostname using SNMP GET
        
        Args:
            device_ip: IP address of the device
            community: SNMP community string (default: self.snmp_community)
            
        Returns:
            dict with hostname and query status
        """
        if community is None:
            community = self.snmp_community
        
        result = {
            'hostname': None,
            'query_success': False,
            'error': None
        }
        
        try:
            # OID for ZTE hostname: 1.3.6.1.4.1.3902.1082.20.10.1.2.0
            hostname_oid = ObjectIdentity('1.3.6.1.4.1.3902.1082.20.10.1.2.0')
            
            # Perform SNMP GET (always use port 161 for SNMP queries)
            iterator = getCmd(
                CommunityData(community),
                UdpTransportTarget((device_ip, 161), timeout=self.snmp_timeout, retries=self.snmp_retries),
                ContextData(),
                ObjectType(hostname_oid)
            )
            
            error_indication, error_status, error_index, var_binds = next(iterator)
            
            if error_indication:
                result['error'] = str(error_indication)
                logger.warning(f"SNMP query failed for {device_ip}: {error_indication}")
            elif error_status:
                result['error'] = f"{error_status.prettyPrint()} at {error_index and var_binds[int(error_index) - 1][0] or '?'}"
                logger.warning(f"SNMP query error for {device_ip}: {result['error']}")
            else:
                # Successfully retrieved hostname
                for var_bind in var_binds:
                    oid, value = var_bind
                    result['hostname'] = str(value)
                    result['query_success'] = True
                    logger.info(f"Retrieved hostname from {device_ip}: {result['hostname']}")
                    
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Exception querying hostname from {device_ip}: {e}")
        
        return result
    
    def trap_callback(self, snmp_engine, state_reference, context_engine_id,
                     context_name, var_binds, cb_ctx):
        """Callback function for received SNMP traps"""
        try:
            # Get transport information
            transport_domain, transport_address = snmp_engine.msgAndPduDsp.getTransportInfo(
                state_reference
            )
            
            source_ip = transport_address[0]
            source_port = transport_address[1]
            
            logger.info(f"Received SNMP trap from {source_ip}:{source_port}")
            
            # Parse trap data with MIB lookups
            trap_data, trap_info, system_info = self.parse_trap_data(var_binds)
            
            # Get trap OID for type detection
            trap_oid = None
            for oid, data in trap_data.items():
                if data.get('is_trap_oid'):
                    trap_oid = data.get('value')
                    break
            
            # Check if this is an ONT registration trap
            is_registration = self.ont_decoder.is_registration_trap(trap_oid) if trap_oid else False
            
            # Check if this is an NMS hello/keepalive trap
            is_nms_hello = self.nms_decoder.is_nms_hello_trap(trap_oid) if trap_oid else False
            
            # Get manufacturer information from trap OID
            manufacturer_info = ManufacturerLookup.get_manufacturer(trap_oid) if trap_oid else {}
            
            # Parse SNMP Engine ID - Note: context_engine_id is the RECEIVER's engine ID
            # The sender's engine ID may be in the trap data itself (check var_binds)
            receiver_engine_id = None
            sender_engine_id = None
            
            if context_engine_id:
                receiver_engine_id = context_engine_id.prettyPrint()
                logger.debug(f"Receiver Engine ID: {receiver_engine_id}")
            
            # Check if sender's engine ID is in var_binds
            # Common OIDs for engine ID:
            # - 1.3.6.1.6.3.10.2.1.1.0 (snmpEngineID from SNMP-FRAMEWORK-MIB)
            # - Some vendors may include it in enterprise-specific OIDs
            for oid, data in trap_data.items():
                oid_lower = oid.lower()
                value = data.get('value', '')
                
                # Check for standard SNMP Engine ID OID
                if '1.3.6.1.6.3.10.2.1.1' in oid:
                    sender_engine_id = value
                    logger.info(f"Found sender's Engine ID in var_binds: {sender_engine_id}")
                    break
                
                # Check if value looks like an engine ID (hex string starting with 80)
                if isinstance(value, str) and len(value) >= 10:
                    # Engine IDs typically start with 0x80 or just 80
                    if value.startswith('0x80') or value.startswith('80'):
                        # This might be an engine ID
                        logger.debug(f"Potential Engine ID found at OID {oid}: {value}")
            
            # Use sender's engine ID if found, otherwise fall back to receiver's for logging
            engine_id_to_parse = sender_engine_id if sender_engine_id else receiver_engine_id
            
            # Add engine IDs to system info
            if engine_id_to_parse:
                system_info['snmpEngineID'] = engine_id_to_parse
                system_info['snmpEngineID_source'] = 'sender' if sender_engine_id else 'receiver'
                
                # Parse the engine ID for more details
                engine_id_parsed = ManufacturerLookup.parse_snmp_engine_id(engine_id_to_parse)
                system_info['snmpEngineID_parsed'] = engine_id_parsed
                
                # Log the parsed engine ID
                logger.info(f"SNMP Engine ID ({system_info['snmpEngineID_source']}): {engine_id_to_parse}")
                if 'enterprise_name' in engine_id_parsed:
                    logger.info(f"  Enterprise: {engine_id_parsed.get('enterprise_name')} (ID: {engine_id_parsed.get('enterprise_id')})")
                logger.info(f"  Format: {engine_id_parsed.get('format')}")
                if 'parsed_data' in engine_id_parsed:
                    logger.info(f"  Parsed Data: {engine_id_parsed.get('parsed_data')}")
            
            if receiver_engine_id and sender_engine_id:
                # Store both if we have both
                system_info['receiver_engine_id'] = receiver_engine_id
            
            # Query device for hostname via SNMP GET
            hostname_info = self.query_device_hostname(source_ip)
            if hostname_info['query_success']:
                system_info['device_hostname'] = hostname_info['hostname']
                logger.info(f"Device hostname: {hostname_info['hostname']}")
            else:
                system_info['device_hostname'] = None
                if hostname_info['error']:
                    logger.debug(f"Could not retrieve hostname: {hostname_info['error']}")
            
            # Build base message for Kafka
            message = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'source_ip': source_ip,
                'source_port': source_port,
                'trap_oid': trap_oid,
                'manufacturer': manufacturer_info.get('manufacturer'),
                'enterprise_id': manufacturer_info.get('enterprise_id'),
                'is_enterprise_trap': manufacturer_info.get('is_enterprise', False),
                'is_standard_trap': manufacturer_info.get('is_standard', False),
                'is_registration': is_registration,
                'is_nms_hello': is_nms_hello,
                'system_info': system_info,
                'trap_data': trap_data,
                'context_engine_id': context_engine_id.prettyPrint() if context_engine_id else None,
                'context_name': context_name.prettyPrint() if context_name else None
            }
            
            # Add trap notification info if found
            if trap_info:
                message['trap_info'] = {
                    'name': trap_info['name'],
                    'description': trap_info['description'],
                    'module': trap_info.get('module')
                }
                logger.info(f"Trap type: {trap_info['name']} (Manufacturer: {manufacturer_info.get('manufacturer', 'Unknown')})")
            else:
                if manufacturer_info.get('manufacturer'):
                    logger.info(f"Manufacturer: {manufacturer_info.get('manufacturer')} (Enterprise ID: {manufacturer_info.get('enterprise_id', 'N/A')})")
            
            # If this is a registration trap, decode and extract ONT info
            if is_registration:
                registration_data = self.ont_decoder.extract_registration_data(trap_data)
                message['registration_data'] = registration_data
                
                logger.info(f"🎯 ONT REGISTRATION DETECTED!")
                logger.info(f"   Serial: {registration_data.get('ont_serial')}")
                logger.info(f"   Model: {registration_data.get('ont_model')}")
                logger.info(f"   Firmware: {registration_data.get('ont_firmware')}")
                logger.info(f"   Time: {registration_data.get('registration_time')}")
                
                # Send to registration-specific topic
                self.send_registration_to_kafka(message, source_ip)
            
            # If this is an NMS hello trap, decode system/interface status
            elif is_nms_hello:
                nms_hello_data = self.nms_decoder.extract_nms_hello_data(trap_data)
                message['nms_hello_data'] = nms_hello_data
                
                # Only log if interface status changed or at reduced frequency
                if nms_hello_data.get('oper_status') == 2:  # Interface down
                    logger.warning(f"⚠️  INTERFACE DOWN DETECTED!")
                    logger.warning(f"   Interface: {nms_hello_data.get('interface_index')}")
                    logger.warning(f"   Type: {nms_hello_data.get('interface_type_name')}")
                    logger.warning(f"   Admin: {nms_hello_data.get('admin_status_name')}")
                    logger.warning(f"   Oper: {nms_hello_data.get('oper_status_name')}")
                else:
                    logger.debug(f"📡 NMS Hello - Uptime: {nms_hello_data.get('system_uptime_formatted')}")
                
                # Send to NMS hello-specific topic (optional)
                # self.send_nms_hello_to_kafka(message, source_ip)
            
            # Log the trap details
            logger.info(f"Trap details: {json.dumps(message, indent=2)}")
            
            # Send to general trap topic
            self.send_to_kafka(message, source_ip)
            
        except Exception as e:
            logger.error(f"Error processing trap: {e}", exc_info=True)
    
    def send_to_kafka(self, message, source_ip):
        """Send parsed trap to Kafka"""
        topic = os.getenv('KAFKA_TOPIC', 'olt_snmp_traps')
        
        try:
            # Use source IP as key for partitioning
            future = self.kafka_producer.send(
                topic,
                key=source_ip,
                value=message
            )
            
            # Wait for send to complete (with timeout)
            record_metadata = future.get(timeout=10)
            
            logger.info(
                f"Sent to Kafka - Topic: {record_metadata.topic}, "
                f"Partition: {record_metadata.partition}, "
                f"Offset: {record_metadata.offset}"
            )
            
        except KafkaError as e:
            logger.error(f"Failed to send to Kafka: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending to Kafka: {e}")
    
    def send_registration_to_kafka(self, message, source_ip):
        """Send ONT registration event to separate Kafka topic"""
        topic = os.getenv('KAFKA_REGISTRATION_TOPIC', 'olt_ont_registration')
        
        try:
            # Build simplified registration message
            registration_msg = {
                'timestamp': message['timestamp'],
                'source_ip': message['source_ip'],
                'event_type': 'ont_registration',
                'ont_data': message.get('registration_data', {}),
                'trap_oid': message.get('trap_oid')
            }
            
            # Use ONT serial as key if available, otherwise source IP
            ont_serial = message.get('registration_data', {}).get('ont_serial')
            key = ont_serial if ont_serial else source_ip
            
            future = self.kafka_producer.send(
                topic,
                key=key,
                value=registration_msg
            )
            
            # Wait for send to complete (with timeout)
            record_metadata = future.get(timeout=10)
            
            logger.info(
                f"✅ Registration sent to Kafka - Topic: {record_metadata.topic}, "
                f"Partition: {record_metadata.partition}, "
                f"Offset: {record_metadata.offset}"
            )
            
        except KafkaError as e:
            logger.error(f"Failed to send registration to Kafka: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending registration to Kafka: {e}")
    
    def run(self):
        """Start the SNMP trap receiver"""
        logger.info("Starting SNMP Trap to Kafka service...")
        logger.info("Press Ctrl+C to stop")
        
        try:
            self.snmp_engine.transportDispatcher.jobStarted(1)
            self.snmp_engine.transportDispatcher.runDispatcher()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.snmp_engine.transportDispatcher.closeDispatcher()
            if self.kafka_producer:
                self.kafka_producer.flush()
                self.kafka_producer.close()
            if self.mib_lookup:
                self.mib_lookup.close()
            logger.info("Service stopped")


def main():
    """Main entry point"""
    try:
        service = SNMPTrapToKafka()
        service.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
