#!/usr/bin/env python3
"""HuggingFace Spaces startup - ASCII-only output for clean error capture."""
import sys, os, traceback

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

print("STARTUP BEGIN", flush=True)
print(f"PY={sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", flush=True)
print(f"CWD={os.getcwd()}", flush=True)

import glob, ast, tokenize, io

print("SYNTAX_CHECK_START", flush=True)
for f in sorted(glob.glob("*.py")):
    if f in ("startup.py", "build_check.py"):
        continue
    try:
        with open(f, encoding="utf-8", errors="replace") as fp:
            src = fp.read()
        try:
            list(tokenize.generate_tokens(io.StringIO(src).readline))
        except tokenize.TokenError as te:
            print(f"TOKEN_ERR {f} {str(te)[:80]}", flush=True)
            sys.exit(1)
        except Exception as te:
            print(f"TOKEN_WARN {f} {type(te).__name__}", flush=True)
        ast.parse(src, filename=f)
        print(f"OK {f}", flush=True)
    except SyntaxError as e:
        print(f"SYNTAX_ERR FILE={f} LINE={e.lineno} MSG={e.msg}", flush=True)
        try:
            txt = repr(e.text).encode('ascii', errors='replace').decode('ascii')
            print(f"SYNTAX_ERR TEXT={txt}", flush=True)
        except Exception:
            pass
        sys.exit(1)
    except Exception as e:
        print(f"FILE_ERR {f} {type(e).__name__}", flush=True)

print("SYNTAX_CHECK_DONE", flush=True)

print("IMPORT_MAIN_START", flush=True)
try:
    import main
    print("IMPORT_MAIN_OK", flush=True)
except SyntaxError as e:
    fn = getattr(e, 'filename', 'unknown') or 'unknown'
    fn_ascii = fn.encode('ascii', errors='replace').decode('ascii')
    print(f"SYNTAX_ERR_IMPORT FILE={fn_ascii} LINE={e.lineno} MSG={e.msg}", flush=True)
    sys.exit(1)
except Exception as e:
    print(f"IMPORT_ERR TYPE={type(e).__name__}", flush=True)
    traceback.print_exc()
    sys.exit(1)

port = int(os.getenv("PORT", "7860"))
print(f"UVICORN_START PORT={port}", flush=True)
import uvicorn
uvicorn.run(main.app, host="0.0.0.0", port=port, log_level="info")
