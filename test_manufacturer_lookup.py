#!/usr/bin/env python3
"""
Test script for manufacturer lookup functionality
"""

# ManufacturerLookup class (copied from snmp_trap_receiver.py)
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


# Test OIDs
test_oids = [
    # ZTE C320 OIDs
    ('1.3.6.1.4.1.3902.1082.500.10.3.1.80', 'ZTE ONT Registration'),
    ('1.3.6.1.4.1.3902.1082.30.20.3.4', 'ZTE NMS Hello'),
    ('1.3.6.1.4.1.3902.1012.3.1.1', 'ZTE GPON'),
    
    # Standard MIB-2 OIDs
    ('1.3.6.1.2.1.2.2.1.7', 'ifAdminStatus'),
    ('1.3.6.1.2.1.2.2.1.8', 'ifOperStatus'),
    ('1.3.6.1.2.1.1.1.0', 'sysDescr'),
    
    # Other vendors
    ('1.3.6.1.4.1.9.9.23.1.2.1.1.6', 'Cisco'),
    ('1.3.6.1.4.1.2011.5.25.31.1.1.1.1', 'Huawei'),
    ('1.3.6.1.4.1.2636.3.1.13.1.1', 'Juniper'),
    ('1.3.6.1.4.1.10002.1.1.1.1.2.1', 'Ubiquiti'),
    
    # SNMPv2
    ('1.3.6.1.6.3.1.1.4.1.0', 'snmpTrapOID'),
    
    # Experimental
    ('1.3.6.1.3.1.1.1.1', 'Experimental MIB'),
]

print("=" * 80)
print("MANUFACTURER LOOKUP TEST")
print("=" * 80)
print()

for oid, description in test_oids:
    info = ManufacturerLookup.get_manufacturer(oid)
    
    print(f"Description: {description}")
    print(f"OID: {oid}")
    print(f"  Manufacturer: {info['manufacturer'] or 'Unknown'}")
    
    if info['enterprise_id']:
        print(f"  Enterprise ID: {info['enterprise_id']}")
    
    if info['is_enterprise']:
        print(f"  Type: Enterprise-specific")
    elif info['is_standard']:
        print(f"  Type: IETF Standard MIB")
    
    print()

print("=" * 80)
print("Available Enterprise Numbers:")
print("=" * 80)
for ent_id, name in sorted(ManufacturerLookup.ENTERPRISE_NUMBERS.items(), 
                            key=lambda x: int(x[0])):
    print(f"  {ent_id:6s} - {name}")
