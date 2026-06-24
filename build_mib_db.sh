#!/bin/bash
# Build MIB Database Script - Enhanced for multiple MIB directories

echo "Building MIB database from ZTE C320 and LibreNMS MIB files..."
echo "=================================================================="

# Define MIB directories
MIB_DIRS=(
    "MIB-C320/MIB/gponcmib"
    "mibs/zte"
    "mibs"
)

# Check if MIB directories exist
VALID_DIRS=()
for dir in "${MIB_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "✓ Found: $dir"
        VALID_DIRS+=("$dir")
    else
        echo "✗ Not found: $dir (skipping)"
    fi
done

if [ ${#VALID_DIRS[@]} -eq 0 ]; then
    echo ""
    echo "ERROR: No valid MIB directories found"
    exit 1
fi

# Check if mib_parser.py exists
if [ ! -f "mib_parser.py" ]; then
    echo "ERROR: mib_parser.py not found"
    exit 1
fi

# Install dependencies if needed
echo ""
echo "Checking Python dependencies..."
pip3 install --quiet python-dotenv 2>/dev/null || true

# Run MIB parser with all directories
echo ""
echo "Parsing MIB files from ${#VALID_DIRS[@]} directories..."
python3 mib_parser.py "${VALID_DIRS[@]}" mib_database.db

# Check if database was created
if [ -f "mib_database.db" ]; then
    echo ""
    echo "SUCCESS: MIB database created successfully!"
    echo "Database file: mib_database.db"
    echo "Database size: $(du -h mib_database.db | cut -f1)"
    
    # Show statistics
    echo ""
    echo "Database statistics:"
    python3 query_mib.py stats 2>/dev/null || echo "  (Run 'python3 query_mib.py stats' to see details)"
    
    echo ""
    echo "You can now run the SNMP trap receiver:"
    echo "  python3 snmp_trap_receiver.py"
else
    echo ""
    echo "ERROR: Failed to create MIB database"
    exit 1
fi
