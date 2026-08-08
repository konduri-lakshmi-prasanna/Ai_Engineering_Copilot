from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def ask_groq(prompt: str) -> str:
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def ask_groq_json(prompt: str) -> str:
    """Same as ask_groq but forces the model to return a JSON object,
    so the reasoning step can be parsed programmatically instead of
    scraping free-form text."""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=1500,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content