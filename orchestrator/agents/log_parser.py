import re

# Paths that point into libraries/dependencies rather than your own repo —
# no point fetching these from GitHub, they'll never be in your source.
_IGNORE_SUBSTRINGS = [
    "site-packages", "node_modules", "dist-packages", "venv/", ".venv/",
    "lib/python", "/usr/lib/", "<frozen", "internal/", "vendor/",
]

# Stack-trace-shaped patterns, checked first since they're the most reliable
# signal of "this file is actually implicated in the error."
_PATTERNS = [
    re.compile(r'File "([^"]+)", line \d+'),                              # Python
    re.compile(r'at .*?\(?([.\w/\\-]+\.(?:js|ts|jsx|tsx)):\d+:\d+\)?'), # JS / TS / Node
    re.compile(r'at [\w.$<>]+\(([\w.$-]+\.java):\d+\)'),                 # Java
    re.compile(r'([\w./\\-]+\.go):\d+'),                                  # Go
    re.compile(r'([\w./\\-]+\.rb):\d+:in'),                               # Ruby
]

# Fallback: any bare-looking source file path mentioned anywhere in the log,
# used only if none of the stack-trace patterns above matched anything.
_GENERIC_PATTERN = re.compile(
    r'\b([\w][\w./-]*\.(?:py|js|ts|jsx|tsx|java|go|rb|php|cs|cpp|c|h|hpp))\b'
)

# ── Kubernetes / container-specific signal extractors ──────────────────────

_K8S_OOM_PATTERN = re.compile(
    r'\bOOMKilled\b|\bexit code 137\b|\bOut.?Of.?Memory\b|\bMemoryError\b',
    re.IGNORECASE,
)
_K8S_CRASH_PATTERN = re.compile(
    r'\bCrashLoopBackOff\b|\bCrashLoop\b',
    re.IGNORECASE,
)
_K8S_EXIT_PATTERN = re.compile(r'exit(?:ed)? (?:code|status) (\d+)', re.IGNORECASE)
_K8S_POD_PATTERN = re.compile(
    r'pod[/ ]+([\w.-]+)',
    re.IGNORECASE,
)
_NPM_ERR_PATTERN = re.compile(
    r'npm ERR!|npm run \w+ failed|Exit status \d+|ELIFECYCLE',
    re.IGNORECASE,
)


def extract_file_paths(log_text: str, max_files: int = 5) -> list:
    """
    Scans a stack trace / deploy log for real file paths, so the GitHub
    agent can fetch the files actually implicated in the error instead of
    guessing from a blind window of recent commits.

    Returns an ordered, de-duplicated list of up to `max_files` paths,
    with library/dependency paths filtered out. Returns an empty list if
    nothing file-path-shaped is found, so the caller can fall back to the
    old recent-commits scan.
    """
    found = []

    for pattern in _PATTERNS:
        for match in pattern.findall(log_text):
            path = match if isinstance(match, str) else match[0]
            found.append(path)

    if not found:
        found = _GENERIC_PATTERN.findall(log_text)

    cleaned = []
    seen = set()
    for path in found:
        path = path.strip().lstrip("./").replace("\\", "/")

        if any(bad in path for bad in _IGNORE_SUBSTRINGS):
            continue
        if path in seen:
            continue

        seen.add(path)
        cleaned.append(path)

        if len(cleaned) >= max_files:
            break

    return cleaned


def detect_error_type(log_text: str) -> dict:
    """
    Analyses a log for high-level error category signals to guide
    agent specialisation decisions.

    Returns a dict with keys:
        is_oom          – True if OOMKilled / MemoryError signals found
        is_crashloop    – True if CrashLoopBackOff signals found
        is_npm_failure  – True if npm build / script failure signals found
        exit_codes      – list of integer exit codes found in the log
        pod_names       – list of Kubernetes pod name fragments found
    """
    is_oom = bool(_K8S_OOM_PATTERN.search(log_text))
    is_crashloop = bool(_K8S_CRASH_PATTERN.search(log_text))
    is_npm_failure = bool(_NPM_ERR_PATTERN.search(log_text))

    raw_exit_codes = _K8S_EXIT_PATTERN.findall(log_text)
    exit_codes = list({int(c) for c in raw_exit_codes})

    pod_matches = _K8S_POD_PATTERN.findall(log_text)
    pod_names = list(dict.fromkeys(pod_matches))[:5]   # ordered unique

    return {
        "is_oom": is_oom,
        "is_crashloop": is_crashloop,
        "is_npm_failure": is_npm_failure,
        "exit_codes": exit_codes,
        "pod_names": pod_names,
    }