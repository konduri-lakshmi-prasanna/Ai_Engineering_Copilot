from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# llama-3.3-70b-versatile was shut down by Groq on 16 Aug 2026.
# Groq's recommended replacement is openai/gpt-oss-120b. You can override the
# model without touching code by adding GROQ_MODEL=<model id> to your .env.
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


def ask_groq(prompt: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        # gpt-oss is a reasoning model: reasoning tokens count toward this
        # limit, so keep it generous or the answer can get cut off.
        max_tokens=4000,
        extra_body={"reasoning_effort": "low"},
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def ask_groq_json(prompt: str) -> str:
    """Same as ask_groq but forces the model to return a JSON object,
    so the reasoning step can be parsed programmatically instead of
    scraping free-form text."""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=6000,
        extra_body={"reasoning_effort": "low"},
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content