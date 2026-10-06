---
title: Python ModuleNotFoundError / ImportError
tags: python, import, module, pip, requirements, dependency, ModuleNotFoundError
url: https://docs.python.org/3/tutorial/modules.html
---
"ModuleNotFoundError: No module named 'x'" means Python's import system
could not find that package in any directory on sys.path. Most common causes
in a deployment context: the package is missing from requirements.txt so the
deploy environment never installed it, the app is running in a different
virtual environment than the one it was tested in, the package name differs
from the import name (e.g. installing "pyyaml" but importing "yaml" is
correct, while installing the wrong similarly-named package is not), or a
local module was renamed/moved without updating the import path. Fix: add
the exact package (and pinned version) to requirements.txt, confirm the
deploy platform actually runs `pip install -r requirements.txt` before
start, and check for typos or case mismatches in the import statement.