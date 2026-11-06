# UI smoke test

Loads the real web page in [jsdom](https://github.com/jsdom/jsdom) against the real server running on fake hardware
(PN532 simulator), then drives it: login, status, tag read/write, settings, log, language switch, logout.
It caught a real bug that no Python test could see.

```
cd tests/ui && npm install        # installs jsdom
python3 -m pytest ../test_ui_smoke.py -q
```

The pytest wrapper is skipped when Node.js or jsdom is missing.
