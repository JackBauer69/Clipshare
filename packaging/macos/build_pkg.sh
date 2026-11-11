#!/bin/sh
set -eu

VERSION="${CLIPSHARE_VERSION:-0.1.0}"
APP="build/frozen/ClipShare.app"
ARTIFACTS="build/artifacts"
UNSIGNED="$ARTIFACTS/ClipShare-${VERSION}-macos-unsigned.pkg"
OUTPUT="$ARTIFACTS/ClipShare-${VERSION}-macos-${MACOS_ARCH:-native}.pkg"
STATUS="$ARTIFACTS/ClipShare-${VERSION}-macos-${MACOS_ARCH:-native}.signing.txt"

if [ ! -d "$APP" ]; then
  echo "Missing $APP; run scripts/build_app.py first." >&2
  exit 1
fi
mkdir -p "$ARTIFACTS"

if [ -n "${MACOS_APPLICATION_IDENTITY:-}" ]; then
  codesign --deep --force --options runtime --timestamp \
    --sign "$MACOS_APPLICATION_IDENTITY" "$APP"
  codesign --verify --deep --strict "$APP"
  APP_SIGNED=true
else
  APP_SIGNED=false
fi

pkgbuild --component "$APP" --install-location /Applications "$UNSIGNED"
if [ -n "${MACOS_INSTALLER_IDENTITY:-}" ]; then
  productsign --sign "$MACOS_INSTALLER_IDENTITY" "$UNSIGNED" "$OUTPUT"
  rm -f "$UNSIGNED"
  INSTALLER_SIGNED=true
else
  mv "$UNSIGNED" "$OUTPUT"
  INSTALLER_SIGNED=false
fi

NOTARIZED=false
if [ -n "${APPLE_API_KEY_PATH:-}" ] && [ -n "${APPLE_API_KEY_ID:-}" ] && [ -n "${APPLE_API_ISSUER_ID:-}" ]; then
  xcrun notarytool submit "$OUTPUT" \
    --key "$APPLE_API_KEY_PATH" \
    --key-id "$APPLE_API_KEY_ID" \
    --issuer "$APPLE_API_ISSUER_ID" \
    --wait
  xcrun stapler staple "$OUTPUT"
  NOTARIZED=true
fi

{
  echo "APP_SIGNED=$APP_SIGNED"
  echo "INSTALLER_SIGNED=$INSTALLER_SIGNED"
  echo "NOTARIZED=$NOTARIZED"
} > "$STATUS"

echo "Created $OUTPUT"
