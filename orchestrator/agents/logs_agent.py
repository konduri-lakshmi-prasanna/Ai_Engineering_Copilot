import re

def logs_agent(log_text: str) -> dict:
    """
    Takes raw log text and extracts errors/exceptions.
    For now, works on plain text passed directly or read from a file.
    """
    lines = log_text.splitlines()

    error_lines = [
        line for line in lines
        if re.search(r"(error|exception|fail|traceback)", line, re.IGNORECASE)
    ]

    return {
        "total_lines": len(lines),
        "error_count": len(error_lines),
        "errors": error_lines[:20],  # cap for readability
    }