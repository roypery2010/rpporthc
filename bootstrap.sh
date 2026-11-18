#!/usr/bin/env bash
# Build the self-hosted Porth compiler from its FASM bootstrap image.
# Stage 0 is the checked-in assembly image. It compiles rpporthc.porth into
# stage 1, stage 1 compiles itself into stage 2, and stage 2 compiles itself
# into stage 3. Because the compiler now applies its own IR optimizer, the
# image produced by the previous compiler (stage 1) is not expected to match
# the next one; the fixed point is reached one generation later, so stage 2
# and stage 3 must be byte-identical.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BUILD="$ROOT/build"
FASM=${RPPORTHC_FASM:-fasmarm}

cd "$ROOT"

if ! command -v "$FASM" >/dev/null 2>&1; then
    echo "bootstrap: error: fasm not found (set RPPORTHC_FASM)" >&2
    exit 1
fi

QEMU=
if [ "$(uname -m)" != "x86_64" ]; then
    for candidate in qemu-x86_64 qemu-x86_64-static; do
        if command -v "$candidate" >/dev/null 2>&1; then
            QEMU=$candidate
            break
        fi
    done
    if [ -z "$QEMU" ]; then
        echo "bootstrap: error: qemu-x86_64 is required to run the x86_64 compiler on $(uname -m)" >&2
        exit 1
    fi
fi

run_binary() {
    if [ -n "$QEMU" ]; then
        "$QEMU" "$@"
    else
        "$@"
    fi
}

mkdir -p "$BUILD"
stage0="$BUILD/porth-stage0"
stage1="$BUILD/porth-stage1"
stage2="$BUILD/porth-stage2"
stage3="$BUILD/porth-stage3"

echo "[1/4] assembling stage 0"
"$FASM" -m 524288 "$ROOT/bootstrap/rpporthc-linux-x86_64.fasm" "$stage0" >/dev/null
chmod +x "$stage0"

echo "[2/4] stage 0 compiles the compiler"
run_binary "$stage0" com -s -o "$stage1" rpporthc.porth
rm -f "$ROOT/rpporthc.asm"

echo "[3/4] stage 1 compiles the compiler"
run_binary "$stage1" com -s -o "$stage2" rpporthc.porth

echo "[4/4] stage 2 compiles the compiler"
run_binary "$stage2" com -s -o "$stage3" rpporthc.porth

if ! cmp -s "$stage2" "$stage3"; then
    echo "bootstrap: error: stage 2 and stage 3 differ; the compiler did not reach a fixed point" >&2
    exit 1
fi

cp "$stage3" "$BUILD/porth"
chmod +x "$BUILD/porth"

tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/rpporthc-bootstrap.XXXXXX")
trap 'rm -rf "$tmpdir"' EXIT
run_binary "$BUILD/porth" com -s -o "$tmpdir/hello" examples/hello-world.porth
actual=$(run_binary "$tmpdir/hello")
if [ "$actual" != "Hello, World" ]; then
    echo "bootstrap: error: compiled hello-world printed $actual" >&2
    exit 1
fi

echo "bootstrap: ok: $BUILD/porth (stage 2 and stage 3 are byte-identical)"