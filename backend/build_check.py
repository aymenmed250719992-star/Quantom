#!/usr/bin/env python3
"""Build-time syntax checker — run inside Docker to detect errors early."""
import glob, ast, sys, tokenize, io

print(f"Python {sys.version}")
ok = True
for f in sorted(glob.glob("*.py")):
    if f == "build_check.py":
        continue
    try:
        with open(f, encoding="utf-8") as fp:
            src = fp.read()
        # Tokenize first (catches imaginary literal errors)
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(src).readline))
        except tokenize.TokenError as te:
            print(f"TOKEN ERR  {f}: {te}")
            ok = False
            continue
        except IndentationError as ie:
            print(f"INDENT ERR {f}:{ie.lineno}: {ie.msg} | {repr(ie.text)}")
            ok = False
            continue
        # AST parse
        ast.parse(src, filename=f)
        print(f"OK  {f}")
    except SyntaxError as e:
        print(f"SYNTAX ERR {f}:{e.lineno}:{e.offset}: {e.msg} | {repr(e.text)}")
        ok = False
    except Exception as e:
        print(f"ERR        {f}: {type(e).__name__}: {e}")
        ok = False

if ok:
    print("All files OK")
    sys.exit(0)
else:
    print("SYNTAX ERRORS FOUND — build aborted")
    sys.exit(1)
