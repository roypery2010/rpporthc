# rpporthc

Roy Perry's Porth Compiler. The compiler is self-hosted: `rpporthc.porth` and
`src/*.porth` implement the lexer, type checker and x86_64 FASM code generator
in Porth itself. `bootstrap/rpporthc-linux-x86_64.fasm` is the stage-0 image used
to build it, and the bootstrap reaches a byte-identical stage 1/stage 2 fixed
point.

The Python implementation in `rpporthc/` remains available through
`bin/rpporthc` as an independent cross-target compiler for AArch64, RISC-V 64
and C (and as an alternative x86_64 implementation). The vendored `std/`
library, `tests/cases/` and `examples/` come from the upstream Porth project,
so existing Porth programs should build unchanged.

## Requirements

- Self-hosted compiler: [`fasm`](https://flatassembler.net/download.php), the
  flat assembler. On a non-x86_64 host it also needs `qemu-x86_64` to run the
  bootstrap and generated x86_64 binaries. Python is not required.
- Python cross-target compiler: Python 3.10 or newer.
- AArch64 target: [`fasmarm`](https://flatassembler.net/download.php), the ARM
  add-on for the flat assembler. It emits the final executable directly; no
  cross-binutils or linker are needed.
- RISC-V 64 target: `llvm-mc` plus `ld.lld` (or `clang` with LLD)
- C target: any host C compiler (`cc`, `gcc` or `clang`)

Tool paths can be overridden with `RPPORTHC_FASM`, `RPPORTHC_FASMARM`,
`RPPORTHC_LD`, `RPPORTHC_CLANG` and `RPPORTHC_CC`.

## Self-hosting

`bootstrap.sh` assembles the checked-in stage-0 image, uses it to compile
`rpporthc.porth`, and then has each freshly built compiler compile itself again.
Because the compiler applies its own IR optimizer, the first self-compiled
image is not expected to match; the fixed point is reached one generation
later:

```console
$ RPPORTH_FASM=fasm bash ./bootstrap.sh
[1/4] assembling stage 0
[2/4] stage 0 compiles the compiler
[3/4] stage 1 compiles the compiler
[4/4] stage 2 compiles the compiler
bootstrap: ok: build/porth (stage 2 and stage 3 are byte-identical)
```

The result is `build/porth`, available through `bin/porth`:

```console
$ ./bin/porth com -o hello examples/hello-world.porth
$ ./bin/porth com -r examples/hello-world.porth
$ ./bin/porth help
```

The self-hosted compiler emits x86_64 FASM (`-f fasmarm`, the default, with `-f fasm`可通过 `RPPORTHC_FASM` 覆盖), ARM64
FASMARM (`-f fasmarm`) or portable C (`-f c`). The assembly formats invoke
`fasm`/`fasmarm` directly. The C target writes `<output>.c` next to the
executable and builds it with `cc -O2`, so it works on any host with a C
compiler. `-o` selects the executable path, `-r` runs it after compilation,
and `-I DIR` (before `com`) adds an include directory. All targets run a small
IR optimizer (constant folding plus peepholes) before code generation.

The C runtime selects a platform layer at compile time: Linux issues syscalls
directly (translating the numbers on non-x86_64 hosts), `__APPLE__` dispatches
through libc because Apple no longer supports `syscall(2)` on arm64, and
`_WIN32` uses the CRT/Win32 mappings that exist (`open`, `read`, `write`,
`close`, `lseek`, `stat`, `fstat`, `getcwd`, `chdir`, `mkdir`, `unlink`,
`rename`, `access`, `dup2`, `getpid`, `exit`) and reports `ENOSYS` for the rest.
Failures come back as `-errno` on every host.

The syscall numbers in `std/linux.porth` are handles: every backend translates
them, so one program can call `write` on any target. The values that get inlined
as numbers are not handles, and they live in an OS-specific module:

| file | contents |
| --- | --- |
| `std/os.porth` | Linux (default): x86_64 `stat`/`termios`/`winsize` layouts, `O_*`, errno, ioctl requests |
| `std/darwin/os.porth` | macOS: `__DARWIN_STRUCT_STAT64`, 72-byte `termios` with 8-byte `tcflag_t`, Darwin `O_*` and errno, `sin_family` at offset 1 |
| `std/windows/os.porth` | Windows: `_stat64`, CRT `_O_*` with `_O_BINARY`, CRT errno; termios/winsize/sigaction are dummies because the calls are `ENOSYS` |

`-os <name>` picks the module (`-os darwin`, `-os windows`), and it only works
with `-f c`. The generated runtime records which module the program was built
with and refuses to compile for a different OS, so a mismatch is a build error
rather than a wrong read. It also `_Static_assert`s the layouts against the
host's headers, which is how the Darwin and Windows values get checked on those
hosts; `-DRP_NO_ABI_CHECKS` skips both checks, which is only useful to exercise
another branch's code on the wrong host.

```console
$ ./bin/porth com -f c -os darwin -o hello examples/hello-world.porth
$ ./bin/porth com -f c -os windows -o hello examples/hello-world.porth
```

## Cross-target compiler

```console
$ ./bin/rpporthc examples/hello-world.porth
$ ./bin/rpporthc --target aarch64 -o hello examples/hello-world.porth
$ ./bin/rpporthc --target riscv64 -o hello examples/hello-world.porth
$ ./bin/rpporthc --target c -o hello examples/hello-world.porth
```

Run the result immediately with `--run` (arguments after `--` are passed to
the program):

```console
$ ./bin/rpporthc --target aarch64 --run -o hello examples/hello-world.porth
$ ./bin/rpporthc --run -o args examples/name.porth -- one two
```

`--target` defaults to the host architecture. Use `-S PATH` to inspect the
generated assembly/C without assembling, `-S -` to print it to stdout, and
`--check` to parse and type-check only.

Includes are searched relative to the including file, then in the current
directory, `./std`, and the compiler's bundled `std/`; add more with `-I DIR`.

```console
$ ./bin/rpporthc --target x86_64 -I vendor/std -o app app.porth
```

The x86_64 and AArch64 backends generate FASM/FASMARM source and run the flat
assembler themselves; only the RISC-V target needs a separate assembler and
linker. Generated programs use a fixed 8 MiB data stack, grow the native stack
downwards, and use native `call`/`ret` for procedures.

## Testing

```console
$ python3 tests/run_tests.py --compiler selfhost --target x86_64 --no-examples
$ python3 tests/run_tests.py --compiler selfhost --target x86_64 examples
$ python3 tests/run_tests.py --target x86_64 --no-examples
$ RPPORTHC_FASMARM=/path/to/fasmarm python3 tests/run_tests.py --target aarch64 --no-examples
$ python3 tests/run_tests.py --target c
```

The self-hosted compiler passes all 108 runnable cases (2 skipped) and 17 of
the 18 examples. The Python compiler passes the same 108 cases and 16 examples;
it rejects one type-checking construct in `brain.porth`, which the self-hosted
compiler accepts now that `src/` is vendored.

The runner understands the upstream `.txt` case format, compares stdout,
stderr and exit codes, and accepts any compile-time rejection for cases whose
expected diagnostics describe a compile error. Add `-v` for output, `-k TEXT`
to filter by filename, or pass individual `.porth` files.

`snake.porth` builds against the vendored `std/termios.porth`, but it is an
interactive raw-mode game, so the runner skips it.
`child-terminated.porth` and `segfault.porth` test the upstream test harness
rather than the language and are skipped too.

## Project layout

```
rpporthc.porth         self-hosted compiler entry point
src/                Porth lexer, types, parser, checker, optimizer, x86_64 generator
bootstrap/          stage-0 FASM image
bootstrap.sh        three-stage self-host bootstrap
bin/porth           launcher for the self-hosted compiler
build/              stage binaries produced by bootstrap.sh
bin/rpporthc        Python cross-target launcher
rpporthc/           Python lexer, parser, type checker, IR and backends
std/                vendored Porth standard library
tests/              vendored test suite and runner
examples/           vendored example programs
```

## Licence

Porth, its standard library and the self-hosted compiler sources are Copyright
2021 Alexey Kutepov and Porth Contributors, distributed under the MIT licence
in `LICENSE`.
