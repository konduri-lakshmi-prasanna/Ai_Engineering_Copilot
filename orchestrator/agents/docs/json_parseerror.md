---
title: JSON parse / unexpected token error
tags: json, parse error, unexpected token, syntaxerror, json.loads, JSON.parse
url: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/JSON/parse
---
A JSON parse error (JavaScript's "Unexpected token ... in JSON" or Python's
json.JSONDecodeError) means the text handed to the parser wasn't valid JSON
at the point it failed. Common causes in a web app: the backend returned an
HTML error page (like a 404 or 500 page) instead of JSON, and the frontend
tried to parse it anyway without checking the response status first; a
trailing comma or unquoted key in a hand-written JSON/config file; or an
LLM response that included extra text/markdown fences around the JSON
instead of raw JSON. Fix: check the response status code before parsing,
log the raw text on failure to see what was actually returned, and if
parsing an LLM output, strip code fences and any leading/trailing text.