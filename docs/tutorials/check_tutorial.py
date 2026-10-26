#!/usr/bin/env python3
# Copyright 2026 The ros2_statechart Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Run a tutorial's commands as written, so that the text and the code agree.

A fenced block is checked when an HTML comment directly above it says how:

    <!-- check: file PATH -->          the block equals the file PATH (from the repo root)
    <!-- check: start -->              run the block in the background (a "terminal")
    <!-- check: run -->                run the block; it must exit with 0
    <!-- check: run expect "TEXT" within 20 -->
                                       run it again every second, for up to 20 s,
                                       until it exits with 0 and prints TEXT
    <!-- check(nightly): ... -->       only with --tag nightly

Blocks run with bash in the order of the file, in the environment of this
script (source the workspace first); the background ones are stopped at the
end. Usage: check_tutorial.py [--tag TAG] TUTORIAL.md...
"""

import argparse
import os
import re
import shlex
import signal
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DIRECTIVE = re.compile(r'<!--\s*check(?:\((?P<tag>[\w-]+)\))?:\s*(?P<body>.*?)\s*-->')
FENCE = re.compile(r'^```')


def blocks(text):
    """Yield (line, tag, directive, code) for every block with a directive."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = DIRECTIVE.fullmatch(lines[i].strip())
        if m and i + 1 < len(lines) and FENCE.match(lines[i + 1]):
            j = i + 2
            while j < len(lines) and not FENCE.match(lines[j]):
                j += 1
            yield i + 1, m.group('tag'), m.group('body'), '\n'.join(lines[i + 2:j]) + '\n'
            i = j
        i += 1


def run_until(code, expect, within):
    deadline = time.monotonic() + within
    while True:
        r = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', code],
                           capture_output=True, text=True, timeout=max(within, 60))
        ok = r.returncode == 0 and (expect is None or expect in r.stdout)
        if ok or time.monotonic() > deadline:
            return ok, r
        time.sleep(1.0)


def check(path, tag):
    with open(path) as f:
        text = f.read()
    background = []
    failures = 0
    try:
        for line, block_tag, directive, code in blocks(text):
            if block_tag != tag:
                continue
            words = shlex.split(directive)
            where = f'{path}:{line}'
            if words[0] == 'file':
                with open(os.path.join(ROOT, words[1])) as f:
                    if f.read() != code:
                        print(f'{where}: block differs from {words[1]}')
                        failures += 1
                    else:
                        print(f'{where}: same as {words[1]}')
            elif words[0] == 'start':
                print(f'{where}: start {code.strip().splitlines()[0]}', flush=True)
                background.append(subprocess.Popen(['bash', '-c', code], start_new_session=True))
            elif words[0] == 'run':
                expect = words[words.index('expect') + 1] if 'expect' in words else None
                within = float(words[words.index('within') + 1]) if 'within' in words else 0
                ok, r = run_until(code, expect, within)
                print(f'{where}: {"ok" if ok else "FAILED"}: {code.strip().splitlines()[0]}',
                      flush=True)
                if not ok:
                    print(f'exit {r.returncode}\n--- stdout\n{r.stdout}\n--- stderr\n{r.stderr}')
                    failures += 1
                    break
            else:
                print(f'{where}: unknown directive {directive!r}')
                failures += 1
    finally:
        for p in background:
            try:
                os.killpg(p.pid, signal.SIGINT)
                p.wait(timeout=10)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                os.killpg(p.pid, signal.SIGKILL)
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--tag', default=None)
    parser.add_argument('tutorials', nargs='+')
    args = parser.parse_args()
    failures = sum(check(p, args.tag) for p in args.tutorials)
    print('all checked blocks pass' if not failures else f'{failures} block(s) failed')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
