import os

# BUG: forgot to load from environment, hardcoded to None
DATABASE_URL = None

def connect():
    if DATABASE_URL is None:
        raise ValueError("Database URL is null — connection failed")
    print(f"Connecting to {DATABASE_URL}")