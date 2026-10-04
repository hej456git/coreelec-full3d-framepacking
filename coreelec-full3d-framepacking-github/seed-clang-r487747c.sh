#!/usr/bin/env bash
# Seed CoreELEC's source cache with Android clang-r487747c without relying on
# the currently unreliable Gitiles-generated archive or CE/LE mirrors.
set -euo pipefail

ROOT="${1:-$PWD}"
CLANG_VERSION="r487747c"
CLANG_REV="clang-${CLANG_VERSION}"
AOSP_BRANCH="emu-34-2-release"
AOSP_REPO="https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86"
ORIGINAL_URL="https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/refs/tags/android-14.0.0_r0.118/${CLANG_REV}.tar.gz"

if [[ ! -f "$ROOT/Makefile" ]]; then
  echo "ERROR: '$ROOT' does not look like a CoreELEC source tree." >&2
  echo "Usage: $0 /path/to/CoreELEC" >&2
  exit 1
fi

for cmd in git tar sha256sum grep; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR: missing required command: $cmd" >&2
    exit 1
  }
done

CLANG_MK="$(grep -RIl --include=package.mk '^PKG_NAME="clang"$' "$ROOT/packages" "$ROOT/projects" 2>/dev/null | head -n1 || true)"
if [[ -z "$CLANG_MK" ]]; then
  echo "ERROR: could not locate the CoreELEC clang package.mk" >&2
  exit 2
fi

if ! grep -q '^PKG_VERSION="r487747c"$' "$CLANG_MK"; then
  echo "ERROR: clang package is not the expected r487747c baseline:" >&2
  grep -E '^PKG_(NAME|VERSION|URL|SHA256)=' "$CLANG_MK" >&2 || true
  exit 2
fi

echo "Using clang package definition: $CLANG_MK"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Fetching $CLANG_REV from AOSP branch $AOSP_BRANCH ..."
git clone --depth 1 --filter=blob:none --sparse --branch "$AOSP_BRANCH" \
  "$AOSP_REPO" "$TMP/aosp-clang"
git -C "$TMP/aosp-clang" sparse-checkout set "$CLANG_REV"

if [[ ! -x "$TMP/aosp-clang/$CLANG_REV/bin/clang" ]]; then
  echo "ERROR: AOSP checkout did not contain $CLANG_REV/bin/clang" >&2
  exit 3
fi

ARCHIVE="$TMP/$CLANG_REV.tar.gz"
tar -C "$TMP/aosp-clang/$CLANG_REV" -czf "$ARCHIVE" .
SHA="$(sha256sum "$ARCHIVE" | awk '{print $1}')"

# CoreELEC's downloader considers an archive cached only when the archive and
# its .sha256 and .url stamp files all exist.
CACHE_DIR="$ROOT/sources/clang"
CACHE_FILE="$CACHE_DIR/$CLANG_REV.tar.gz"
mkdir -p "$CACHE_DIR"
cp "$ARCHIVE" "$CACHE_FILE"
printf '%s\n' "$SHA" > "$CACHE_FILE.sha256"
printf '%s\n' "$ORIGINAL_URL" > "$CACHE_FILE.url"

echo
echo "Seeded CoreELEC clang source cache:"
echo "  $CACHE_FILE"
echo "  $CACHE_FILE.sha256"
echo "  $CACHE_FILE.url"
echo "SHA256: $SHA"
echo
echo "Pre-flight test:"
echo "  cd '$ROOT'"
echo "  PROJECT=Amlogic-ce DEVICE=Amlogic-no ARCH=aarch64 scripts/get clang"
echo
echo "Then resume:"
echo "  PROJECT=Amlogic-ce DEVICE=Amlogic-no ARCH=aarch64 make"
