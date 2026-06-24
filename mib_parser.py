#!/usr/bin/env python3
"""
MIB Parser - Parses ZTE C320 MIB files and stores OID mappings in SQLite
"""

import os
import re
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MIBParser:
    """Parse MIB files and extract OID definitions"""
    
    # Common OID prefixes - Extended with LibreNMS findings and standard SNMP prefixes
    OID_PREFIXES = {
        # Standard SNMP tree (RFC 1155, RFC 1213)
        'iso': '1',
        'org': '1.3',
        'dod': '1.3.6',
        'internet': '1.3.6.1',
        'directory': '1.3.6.1.1',
        'mgmt': '1.3.6.1.2',
        'mib-2': '1.3.6.1.2.1',
        'experimental': '1.3.6.1.3',
        'private': '1.3.6.1.4',
        'enterprises': '1.3.6.1.4.1',
        'security': '1.3.6.1.5',
        'snmpV2': '1.3.6.1.6',
        'snmpModules': '1.3.6.1.6.3',
        # ZTE vendor-specific OIDs
        'zte': '1.3.6.1.4.1.3902',
        'zxAccessNode': '1.3.6.1.4.1.3902.1082',
        'zxAn': '1.3.6.1.4.1.3902.1082',  # Alias for zxAccessNode
        'zxAnEquipment': '1.3.6.1.4.1.3902.1082.10',
        'zxAnSystem': '1.3.6.1.4.1.3902.1082.20',
        'zxAnInterface': '1.3.6.1.4.1.3902.1082.30',
        'zxEnterpriseMib': '1.3.6.1.4.1.3902',
        'zxPON': '1.3.6.1.4.1.3902.1012',
        'zxGponRootMib': '1.3.6.1.4.1.3902.1012.3',
        'zxAnPonMib': '1.3.6.1.4.1.3902.1015.1010',
        'zxAnGponMib': '1.3.6.1.4.1.3902.1015.1010.2',
    }
    
    def __init__(self, mib_dirs: list = None):
        if mib_dirs is None:
            mib_dirs = []
        self.mib_dirs = [Path(d) for d in mib_dirs]
        self.oid_map = {}  # name -> oid
        self.reverse_map = {}  # oid -> name
        self.descriptions = {}  # name -> description
        self.object_types = {}  # name -> type info
        self.notifications = {}  # name -> notification info
        
    def parse_all_mibs(self):
        """Parse all MIB files in all directories"""
        all_mib_files = []
        
        for mib_dir in self.mib_dirs:
            logger.info(f"Scanning MIB directory: {mib_dir}")
            
            # Scan for MIB files with various extensions
            mib_files = []
            for pattern in ['*.mib', '*.mi2', '*-MIB', '*MIB', '*SMI']:
                mib_files.extend(mib_dir.glob(f'**/{pattern}'))
            
            # Also include files without extension (common in LibreNMS)
            for file_path in mib_dir.rglob('*'):
                if file_path.is_file() and not file_path.suffix:
                    # Check if it looks like a MIB file
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            first_line = f.readline()
                            if 'DEFINITIONS' in first_line or 'MIB' in first_line:
                                mib_files.append(file_path)
                    except:
                        pass
            
            all_mib_files.extend(mib_files)
            logger.info(f"Found {len(mib_files)} MIB files in {mib_dir}")
        
        logger.info(f"Total MIB files to parse: {len(all_mib_files)}")
        
        for mib_file in all_mib_files:
            try:
                self.parse_mib_file(mib_file)
            except Exception as e:
                logger.debug(f"Error parsing {mib_file.name}: {e}")
        
        logger.info(f"Parsed {len(self.oid_map)} OID definitions")
        logger.info(f"Found {len(self.notifications)} notification definitions")
    
    def parse_mib_file(self, filepath: Path):
        """Parse a single MIB file"""
        logger.debug(f"Parsing {filepath.name}")
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Extract module name
        module_match = re.search(r'(\w+)\s+DEFINITIONS\s*::=\s*BEGIN', content)
        if not module_match:
            return
        
        module_name = module_match.group(1)
        
        # Parse OBJECT IDENTIFIER assignments
        self._parse_object_identifiers(content, module_name)
        
        # Parse OBJECT-TYPE definitions
        self._parse_object_types(content, module_name)
        
        # Parse NOTIFICATION-TYPE definitions
        self._parse_notifications(content, module_name)
    
    def _parse_object_identifiers(self, content: str, module: str):
        """Parse OBJECT IDENTIFIER assignments"""
        # Pattern: name OBJECT IDENTIFIER ::= { parent child }
        pattern = r'(\w+)\s+OBJECT\s+IDENTIFIER\s*::=\s*\{\s*(\w+)\s+(\d+)\s*\}'
        
        for match in re.finditer(pattern, content):
            name = match.group(1)
            parent = match.group(2)
            child = match.group(3)
            
            # Build OID
            if parent in self.oid_map:
                oid = f"{self.oid_map[parent]}.{child}"
            elif parent in self.OID_PREFIXES:
                oid = f"{self.OID_PREFIXES[parent]}.{child}"
            else:
                continue
            
            self.oid_map[name] = oid
            self.reverse_map[oid] = name
    
    def _parse_object_types(self, content: str, module: str):
        """Parse OBJECT-TYPE definitions"""
        # Pattern: name OBJECT-TYPE ... ::= { parent child }
        pattern = r'(\w+)\s+OBJECT-TYPE\s+(.*?)::=\s*\{\s*(\w+)\s+(\d+)\s*\}'
        
        for match in re.finditer(pattern, content, re.DOTALL):
            name = match.group(1)
            definition = match.group(2)
            parent = match.group(3)
            child = match.group(4)
            
            # Build OID
            if parent in self.oid_map:
                oid = f"{self.oid_map[parent]}.{child}"
            elif parent in self.OID_PREFIXES:
                oid = f"{self.OID_PREFIXES[parent]}.{child}"
            else:
                continue
            
            # Extract SYNTAX
            syntax_match = re.search(r'SYNTAX\s+([\w\-]+(?:\s*\(.*?\))?)', definition)
            syntax = syntax_match.group(1) if syntax_match else 'Unknown'
            
            # Extract DESCRIPTION
            desc_match = re.search(r'DESCRIPTION\s+"(.*?)"', definition, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else ''
            
            # Extract MAX-ACCESS
            access_match = re.search(r'MAX-ACCESS\s+([\w\-]+)', definition)
            access = access_match.group(1) if access_match else ''
            
            self.oid_map[name] = oid
            self.reverse_map[oid] = name
            self.descriptions[name] = description
            self.object_types[name] = {
                'oid': oid,
                'syntax': syntax,
                'access': access,
                'description': description,
                'module': module
            }
    
    def _parse_notifications(self, content: str, module: str):
        """Parse NOTIFICATION-TYPE definitions (traps)"""
        # Pattern: name NOTIFICATION-TYPE ... ::= { parent child }
        pattern = r'(\w+)\s+NOTIFICATION-TYPE\s+(.*?)::=\s*\{\s*(\w+)\s+(\d+)\s*\}'
        
        for match in re.finditer(pattern, content, re.DOTALL):
            name = match.group(1)
            definition = match.group(2)
            parent = match.group(3)
            child = match.group(4)
            
            # Build OID
            if parent in self.oid_map:
                oid = f"{self.oid_map[parent]}.{child}"
            elif parent in self.OID_PREFIXES:
                oid = f"{self.OID_PREFIXES[parent]}.{child}"
            else:
                continue
            
            # Extract OBJECTS (variables in trap)
            objects_match = re.search(r'OBJECTS\s*\{(.*?)\}', definition, re.DOTALL)
            objects = []
            if objects_match:
                objects = [o.strip() for o in objects_match.group(1).split(',')]
            
            # Extract DESCRIPTION
            desc_match = re.search(r'DESCRIPTION\s+"(.*?)"', definition, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else ''
            
            self.oid_map[name] = oid
            self.reverse_map[oid] = name
            self.descriptions[name] = description
            self.notifications[name] = {
                'oid': oid,
                'objects': objects,
                'description': description,
                'module': module
            }


class MIBDatabase:
    """SQLite database for MIB OID lookups"""
    
    def __init__(self, db_path: str = 'mib_database.db'):
        self.db_path = db_path
        self.conn = None
        
    def connect(self):
        """Connect to database"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        
    def create_tables(self):
        """Create database tables"""
        cursor = self.conn.cursor()
        
        # OID mappings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS oid_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                oid TEXT NOT NULL,
                module TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index on OID for fast lookups
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_oid ON oid_mappings(oid)
        ''')
        
        # Object types table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS object_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                oid TEXT NOT NULL,
                syntax TEXT,
                access TEXT,
                description TEXT,
                module TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Notifications/Traps table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                oid TEXT NOT NULL,
                objects TEXT,
                description TEXT,
                module TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
        logger.info("Database tables created")
    
    def import_from_parser(self, parser: MIBParser):
        """Import parsed MIB data into database"""
        cursor = self.conn.cursor()
        
        # Clear existing data
        cursor.execute('DELETE FROM oid_mappings')
        cursor.execute('DELETE FROM object_types')
        cursor.execute('DELETE FROM notifications')
        
        # Import OID mappings
        for name, oid in parser.oid_map.items():
            # Try to find module
            module = None
            if name in parser.object_types:
                module = parser.object_types[name]['module']
            elif name in parser.notifications:
                module = parser.notifications[name]['module']
            
            cursor.execute('''
                INSERT OR REPLACE INTO oid_mappings (name, oid, module)
                VALUES (?, ?, ?)
            ''', (name, oid, module))
        
        # Import object types
        for name, info in parser.object_types.items():
            cursor.execute('''
                INSERT OR REPLACE INTO object_types 
                (name, oid, syntax, access, description, module)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, info['oid'], info['syntax'], info['access'], 
                  info['description'], info['module']))
        
        # Import notifications
        for name, info in parser.notifications.items():
            objects_str = ','.join(info['objects'])
            cursor.execute('''
                INSERT OR REPLACE INTO notifications 
                (name, oid, objects, description, module)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, info['oid'], objects_str, info['description'], 
                  info['module']))
        
        self.conn.commit()
        logger.info(f"Imported {len(parser.oid_map)} OID mappings")
        logger.info(f"Imported {len(parser.object_types)} object types")
        logger.info(f"Imported {len(parser.notifications)} notifications")
    
    def lookup_oid(self, oid: str) -> Optional[Dict]:
        """Look up OID and return information"""
        cursor = self.conn.cursor()
        
        # Try exact match first
        cursor.execute('''
            SELECT name, oid, syntax, access, description, module
            FROM object_types WHERE oid = ?
        ''', (oid,))
        
        row = cursor.fetchone()
        if row:
            return dict(row)
        
        # Try prefix match (for table entries like .1.2.3.4.5.1.1.x)
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
                return result
        
        return None
    
    def lookup_name(self, name: str) -> Optional[str]:
        """Look up name and return OID"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT oid FROM oid_mappings WHERE name = ?', (name,))
        row = cursor.fetchone()
        return row['oid'] if row else None
    
    def lookup_notification(self, oid: str) -> Optional[Dict]:
        """Look up notification/trap by OID"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT name, oid, objects, description, module
            FROM notifications WHERE oid = ?
        ''', (oid,))
        
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def search_by_keyword(self, keyword: str) -> List[Dict]:
        """Search OIDs by keyword in name or description"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT name, oid, syntax, description, module
            FROM object_types 
            WHERE name LIKE ? OR description LIKE ?
            LIMIT 50
        ''', (f'%{keyword}%', f'%{keyword}%'))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


def build_mib_database(mib_dirs: list, db_path: str = 'mib_database.db'):
    """Build MIB database from multiple MIB directories"""
    logger.info("Starting MIB database build...")
    logger.info(f"MIB directories: {', '.join(mib_dirs)}")
    
    # Parse MIB files
    parser = MIBParser(mib_dirs)
    parser.parse_all_mibs()
    
    # Create database
    db = MIBDatabase(db_path)
    db.connect()
    db.create_tables()
    db.import_from_parser(parser)
    db.close()
    
    logger.info(f"MIB database created: {db_path}")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python mib_parser.py <mib_directory1> [mib_directory2 ...] [output_db]")
        print("Example: python mib_parser.py MIB-C320/MIB/gponcmib mibs/zte mibs")
        print("         python mib_parser.py MIB-C320/MIB/gponcmib mibs mib_database.db")
        sys.exit(1)
    
    # Determine if last argument is database path
    args = sys.argv[1:]
    if args[-1].endswith('.db'):
        db_path = args[-1]
        mib_dirs = args[:-1]
    else:
        db_path = 'mib_database.db'
        mib_dirs = args
    
    # Validate directories
    valid_dirs = []
    for d in mib_dirs:
        if Path(d).exists():
            valid_dirs.append(d)
        else:
            print(f"Warning: Directory not found: {d}")
    
    if not valid_dirs:
        print("Error: No valid MIB directories found")
        sys.exit(1)
    
    print(f"Building MIB database from {len(valid_dirs)} directories:")
    for d in valid_dirs:
        print(f"  - {d}")
    print(f"Output: {db_path}\n")
    
    build_mib_database(valid_dirs, db_path)
    
    # Test lookups
    print("\n" + "="*60)
    print("Testing database lookups...")
    print("="*60)
    
    db = MIBDatabase(db_path)
    db.connect()
    
    # Test some common OIDs
    test_oids = [
        '1.3.6.1.2.1.1.3.0',  # sysUpTime
        '1.3.6.1.4.1.3902',    # ZTE enterprise
    ]
    
    for oid in test_oids:
        result = db.lookup_oid(oid)
        if result:
            print(f"\nOID: {oid}")
            print(f"  Name: {result['name']}")
            print(f"  Description: {result.get('description', 'N/A')[:100]}")
    
    db.close()
