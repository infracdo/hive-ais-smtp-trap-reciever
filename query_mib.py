#!/usr/bin/env python3
"""
Query MIB Database - Interactive tool to explore the MIB database
"""

import sys
import sqlite3
from pathlib import Path

def connect_db(db_path='mib_database.db'):
    """Connect to MIB database"""
    if not Path(db_path).exists():
        print(f"ERROR: Database not found: {db_path}")
        print("Run 'python3 mib_parser.py' first to build the database")
        sys.exit(1)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def lookup_oid(conn, oid):
    """Look up an OID"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT name, oid, syntax, access, description, module
        FROM object_types WHERE oid = ? OR oid LIKE ?
    ''', (oid, f'{oid}.%'))
    
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"\nOID: {row['oid']}")
            print(f"Name: {row['name']}")
            print(f"Syntax: {row['syntax']}")
            print(f"Access: {row['access']}")
            print(f"Module: {row['module']}")
            print(f"Description: {row['description'][:200]}")
    else:
        print(f"No match found for OID: {oid}")

def lookup_name(conn, name):
    """Look up by name"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT name, oid, syntax, access, description, module
        FROM object_types WHERE name LIKE ?
        LIMIT 20
    ''', (f'%{name}%',))
    
    rows = cursor.fetchall()
    if rows:
        print(f"\nFound {len(rows)} results:")
        for row in rows:
            print(f"\n  Name: {row['name']}")
            print(f"  OID: {row['oid']}")
            print(f"  Syntax: {row['syntax']}")
            print(f"  Module: {row['module']}")
            if row['description']:
                print(f"  Description: {row['description'][:100]}...")
    else:
        print(f"No match found for name: {name}")

def list_notifications(conn):
    """List all notifications/traps"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT name, oid, description, module
        FROM notifications
        ORDER BY module, name
        LIMIT 50
    ''')
    
    rows = cursor.fetchall()
    print(f"\nFound {len(rows)} notifications/traps:")
    for row in rows:
        print(f"\n  Name: {row['name']}")
        print(f"  OID: {row['oid']}")
        print(f"  Module: {row['module']}")
        if row['description']:
            print(f"  Description: {row['description'][:100]}...")

def stats(conn):
    """Show database statistics"""
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) as count FROM oid_mappings')
    oid_count = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM object_types')
    obj_count = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM notifications')
    notif_count = cursor.fetchone()['count']
    
    cursor.execute('SELECT DISTINCT module FROM object_types WHERE module IS NOT NULL')
    modules = [row['module'] for row in cursor.fetchall()]
    
    print("\nMIB Database Statistics:")
    print(f"  Total OID mappings: {oid_count}")
    print(f"  Object types: {obj_count}")
    print(f"  Notifications/Traps: {notif_count}")
    print(f"  Modules: {len(modules)}")
    print(f"\n  Module list:")
    for module in sorted(modules)[:20]:
        print(f"    - {module}")

def main():
    """Main CLI"""
    if len(sys.argv) < 2:
        print("MIB Database Query Tool")
        print("=" * 60)
        print("\nUsage:")
        print("  python3 query_mib.py stats                    - Show database statistics")
        print("  python3 query_mib.py oid <OID>                - Look up by OID")
        print("  python3 query_mib.py name <NAME>              - Search by name")
        print("  python3 query_mib.py traps                    - List all traps")
        print("\nExamples:")
        print("  python3 query_mib.py oid 1.3.6.1.4.1.3902")
        print("  python3 query_mib.py name gpon")
        print("  python3 query_mib.py traps")
        sys.exit(1)
    
    conn = connect_db()
    
    command = sys.argv[1].lower()
    
    if command == 'stats':
        stats(conn)
    elif command == 'oid' and len(sys.argv) > 2:
        lookup_oid(conn, sys.argv[2])
    elif command == 'name' and len(sys.argv) > 2:
        lookup_name(conn, sys.argv[2])
    elif command == 'traps' or command == 'notifications':
        list_notifications(conn)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
    
    conn.close()

if __name__ == '__main__':
    main()
