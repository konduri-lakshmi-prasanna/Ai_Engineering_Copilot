---
title: Python AttributeError / TypeError on NoneType
tags: NoneType, AttributeError, None, python, null
url: https://docs.python.org/3/library/exceptions.html#AttributeError
---
"'NoneType' object has no attribute 'x'" or "unsupported operand type(s)...
NoneType" means a variable that the code assumed would hold a real value
was actually None at that point. Typical causes: a function that returns
None on failure (many dict.get(), re.match(), or DB query methods do this)
whose return value wasn't checked before being used, a variable initialized
to None and never reassigned along some code path, or a config/env value
that was expected to be set but wasn't. Fix: check the value for None
immediately after it's produced, before using it, and either raise a clear
error at that point or supply a safe default — this also makes future
failures much easier to diagnose than a NoneType error several calls later.