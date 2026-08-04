# test_env.py
from dotenv import load_dotenv
import os

load_dotenv()

groq_key = os.getenv("GROQ_API_KEY")
github_token = os.getenv("GITHUB_TOKEN")

print("GROQ_API_KEY loaded:", groq_key[:10] + "..." if groq_key else "NOT FOUND")
print("GITHUB_TOKEN loaded:", github_token[:10] + "..." if github_token else "NOT FOUND")