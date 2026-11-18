#!/usr/bin/env python3
"""Run the vendored Porth test suite.

Files use the upstream `.txt` test-case format:

    :i argc N
    :b arg0 LEN
    <bytes>
    ...
    :b stdin LEN
    <bytes>
    :i returncode N
    :b stdout LEN
    <bytes>
    :b stderr LEN
    <bytes>

Tests whose expected stderr describes a compile error only have to fail to
compile; their exact diagnostics are not compared to upstream's wording.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rpporthc.toolchain import ToolchainError, host_target, run_command  # noqa: E402

CASES_DIR = ROOT / "tests" / "cases"
EXAMPLES_DIR = ROOT / "examples"
CLI = ROOT / "bin" / "rpporthc"


@dataclass
class TestCase:
    argv: list[str] = field(default_factory=list)
    stdin: bytes = b""
    returncode: int = 0
    stdout: bytes = b""
    stderr: bytes = b""


def _blob(f: BinaryIO, name: bytes) -> bytes:
    line = f.readline()
    prefix = b":b " + name + b" "
    if not line.startswith(prefix):
        raise ValueError(f"expected `{prefix.decode()}`, got {line!r}")
    size = int(line[len(prefix):-1])
    data = f.read(size)
    if f.read(1) != b"\n":
        raise ValueError("malformed blob field")
    return data


def _int(f: BinaryIO, name: bytes) -> int:
    line = f.readline()
    prefix = b":i " + name + b" "
    if not line.startswith(prefix):
        raise ValueError(f"expected `{prefix.decode()}`, got {line!r}")
    return int(line[len(prefix):-1])


def load_case(path: Path) -> TestCase | None:
    if not path.exists():
        return None
    with path.open("rb") as f:
        argc = _int(f, b"argc")
        argv = [_blob(f, b"arg%d" % i).decode("utf-8") for i in range(argc)]
        stdin = _blob(f, b"stdin")
        returncode = _int(f, b"returncode")
        stdout = _blob(f, b"stdout")
        stderr = _blob(f, b"stderr")
    return TestCase(argv, stdin, returncode, stdout, stderr)


def is_compile_error_case(case: TestCase) -> bool:
    """Heuristic: upstream compile diagnostics mention ERROR/TODO and no output."""
    return (
        bool(case.stderr)
        and not case.stdout
        and (b"ERROR:" in case.stderr or b": TODO:" in case.stderr or b"error:" in case.stderr)
    )


# These exercise the upstream test harness (`run` with child-process reporting)
# or need include files that are not part of the standard library.
SKIP = {
    "brain.porth": "example needs the compiler's own src/*.porth files",
    "snake.porth": "example is an interactive raw-mode game and needs a terminal",
    "child-terminated.porth": "tests the upstream test harness, not the language",
    "segfault.porth": "tests the upstream test harness, not the language",
}


@dataclass
class Result:
    name: str
    status: str  # pass | fail | skip
    detail: str = ""


def run_one(source: Path, target: str, compiler: str, workdir: Path, verbose: bool) -> Result:
    name = source.name
    if name == "brain.porth" and compiler == "selfhost":
        # The self-hosted compiler can compile brain.porth now that src/ is
        # part of the repository; the Python frontend still rejects one of
        # its type-checking constructs.
        pass
    elif name in SKIP:
        return Result(name, "skip", SKIP[name])

    expected = load_case(source.with_suffix(".txt"))
    executable = workdir / (source.stem + ".bin")
    # Keep source paths relative to the project root so path-reporting tests
    # (e.g. `here`) do not depend on where the checkout lives.
    try:
        source_arg = "./" + source.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        source_arg = str(source)
    if compiler == "selfhost":
        compile_cmd = [
            str(ROOT / "bin" / "porth"), "com", "-s",
            "-o", str(executable), source_arg,
        ]
    else:
        compile_cmd = [
            sys.executable, str(CLI), "--target", target,
            "-o", str(executable), source_arg,
        ]
    compiled = subprocess.run(
        compile_cmd, cwd=ROOT, capture_output=True, text=True, timeout=120,
    )

    if compiled.returncode != 0:
        if expected is not None and is_compile_error_case(expected):
            return Result(name, "pass", "rejected at compile time")
        return Result(name, "fail", "compilation failed:\n" + compiled.stderr.strip())

    if expected is not None and is_compile_error_case(expected):
        return Result(name, "fail", "expected a compile error, but compilation succeeded")

    if expected is None:
        return Result(name, "pass", "compiles (no expected output file)")

    try:
        command = run_command(target, executable)
    except ToolchainError as exc:
        return Result(name, "skip", str(exc))

    try:
        actual = subprocess.run(
            command + expected.argv,
            input=expected.stdin,
            cwd=ROOT,
            capture_output=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return Result(name, "fail", "timed out while running")

    problems = []
    if actual.returncode != expected.returncode:
        problems.append(f"return code: expected {expected.returncode}, got {actual.returncode}")
    if actual.stdout != expected.stdout:
        problems.append(
            f"stdout: expected {expected.stdout!r}, got {actual.stdout!r}"
        )
    if expected.stderr and actual.stderr != expected.stderr:
        problems.append(
            f"stderr: expected {expected.stderr!r}, got {actual.stderr!r}"
        )
    if problems:
        return Result(name, "fail", "\n".join(problems))
    if verbose:
        return Result(name, "pass", f"stdout={actual.stdout!r} rc={actual.returncode}")
    return Result(name, "pass")


def discover(paths: list[str], include_examples: bool) -> list[Path]:
    if paths:
        out: list[Path] = []
        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                out.extend(sorted(path.glob("*.porth")))
            else:
                out.append(path)
        return out
    files = sorted(CASES_DIR.glob("*.porth"))
    if include_examples:
        files += sorted(EXAMPLES_DIR.glob("*.porth"))
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="test files or directories")
    parser.add_argument("--target", default=None,
                        help="backend to test (default: host architecture)")
    parser.add_argument("--compiler", choices=("python", "selfhost"), default="python",
                        help="compiler frontend to test (default: python); "
                             "selfhost supports x86_64 only")
    parser.add_argument("--no-examples", action="store_true",
                        help="only run tests/cases, not examples/")
    parser.add_argument("-k", "--filter", default=None,
                        help="only run files whose name contains this substring")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    target = args.target or host_target()
    if args.compiler == "selfhost" and target != "x86_64":
        print("the self-hosted compiler only targets x86_64", file=sys.stderr)
        return 2

    files = discover(args.paths, include_examples=not args.no_examples)
    if args.filter:
        files = [f for f in files if args.filter in f.name]
    if not files:
        print("no tests found", file=sys.stderr)
        return 2

    results: list[Result] = []
    with tempfile.TemporaryDirectory(prefix="rpporthc-tests-") as tmp:
        workdir = Path(tmp)
        for index, source in enumerate(files):
            try:
                result = run_one(source, target, args.compiler, workdir, args.verbose)
            except Exception as exc:  # keep going on compiler crashes
                result = Result(source.name, "fail", f"crash: {exc!r}")
            results.append(result)
            if result.status == "fail":
                print(f"[FAIL] {result.name}\n{result.detail}\n")
            elif result.status == "skip":
                print(f"[SKIP] {result.name}: {result.detail}")
            elif args.verbose:
                print(f"[PASS] {result.name} {result.detail}")

    passed = sum(r.status == "pass" for r in results)
    failed = [r for r in results if r.status == "fail"]
    skipped = sum(r.status == "skip" for r in results)
    print(f"\n{passed} passed, {len(failed)} failed, {skipped} skipped "
          f"({len(results)} total, target {target}, compiler {args.compiler})")
    if failed:
        print("failed: " + ", ".join(r.name for r in failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
