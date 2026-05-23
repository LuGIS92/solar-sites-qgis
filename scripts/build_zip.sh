#!/usr/bin/env bash
# Build an installable QGIS plugin ZIP.
# Usage:  bash scripts/build_zip.sh
# Output: dist/solar_sites_pv_analysis_vX.X.X.zip
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_SRC="$REPO/qgis_solar_plugin"
SOLAR_SRC="$REPO/solar_sites"
PLUGIN_NAME="solar_sites_pv_analysis"
VERSION=$(grep '^version=' "$PLUGIN_SRC/metadata.txt" | cut -d= -f2)
DIST="$REPO/dist"
BUILD="$DIST/build/$PLUGIN_NAME"

echo "Building $PLUGIN_NAME v$VERSION ..."

# Clean build directory
[ -d "$BUILD" ] && rm -r "$BUILD"
mkdir -p "$BUILD"

# Copy plugin source
cp -r "$PLUGIN_SRC"/. "$BUILD/"

# Bundle the solar_sites library inside the plugin
cp -r "$SOLAR_SRC" "$BUILD/solar_sites"

# Remove Python cache files
find "$BUILD" -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
find "$BUILD" -name "*.pyc" -delete 2>/dev/null || true

# Create ZIP (must contain plugin folder, not its contents)
ZIP_NAME="${PLUGIN_NAME}_v${VERSION}.zip"
(cd "$DIST/build" && zip -qr "$DIST/$ZIP_NAME" "$PLUGIN_NAME")

echo ""
echo "Created: $DIST/$ZIP_NAME"
echo ""
echo "Install in QGIS:"
echo "  Plugins -> Manage and Install Plugins -> Install from ZIP"
