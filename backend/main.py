from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import openai
import requests
from datetime import datetime, timedelta
import asyncio
import json

# Load environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EXA_API_KEY = os.getenv("EXA_API_KEY")

openai.api_key = OPENAI_API_KEY

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatInput(BaseModel):
    message: str
    history: list
    preferences: dict

PREFERENCE_QUESTIONS = [
    ("tone", "What is your preferred tone of voice? (e.g., formal, casual, enthusiastic)"),
    ("format", "What is your preferred response format? (e.g., bullet points, paragraphs)"),
    ("language", "What is your language preference? (e.g., English, Spanish)"),
    ("style", "What interaction style do you prefer? (e.g., concise, detailed)"),
    ("topics", "What are your preferred news topics? (e.g., technology, sports, politics)"),
]

# Simple in-memory cache
news_cache = {}

def make_cache_key(topic, preferences):
    # Use a tuple of topic + frozen preferences dict as the cache key
    key = (topic.strip().lower(), tuple(sorted((k, str(v).strip().lower()) for k, v in preferences.items())))
    return key

def generate_search_query(user_question):
    SYSTEM_MESSAGE = (
        "You are a helpful assistant that generates search queries based on user questions. Only generate one search query."
    )
    completion = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": user_question},
        ],
        max_tokens=64,
        temperature=0.2,
    )
    return completion.choices[0].message.content.strip()

async def summarize_article_async(article_text, preferences):
    SYSTEM_MESSAGE = (
        "You are a helpful assistant that briefly summarizes the content of a webpage. Summarize the user's input."
    )
    language = preferences.get("language", "English")
    tone = preferences.get("tone", "neutral")
    style = preferences.get("style", "concise")
    format_pref = preferences.get("format", "paragraphs")

    # Limit article_text to avoid exceeding context window
    max_chars = 6000
    if len(article_text) > max_chars:
        article_text = article_text[:max_chars]

    user_message = f"Summarize this in {style} style, {tone} tone, in {language}."
    if "bullet" in format_pref.lower():
        user_message += " Respond as bullet points."
    user_message += "\n\n" + article_text

    response = await asyncio.to_thread(
        openai.chat.completions.create,
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": user_message},
        ],
        max_tokens=160,
        temperature=0.4,
    )
    return response.choices[0].message.content.strip()

def exa_search(query, start_published_date, num_results, api_key):
    url = "https://api.exa.ai/search"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "query": query,
        "category": "news",
        "numResults": num_results,
        "text": True,
        "startPublishedDate": start_published_date
    }
    res = requests.post(url, headers=headers, json=payload)
    res.raise_for_status()
    return res.json()

def exa_get_contents(urls, api_key):
    url = "https://api.exa.ai/contents"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "urls": urls,
        "text": True
    }
    res = requests.post(url, headers=headers, json=payload)
    res.raise_for_status()
    return res.json().get("results", [])

@app.post("/chatbot")
async def chatbot_endpoint(inp: ChatInput):
    history = inp.history or []
    preferences = inp.preferences or {}
    user_msg = inp.message.strip()

    print("=== Incoming message ===")
    print("User message:", repr(user_msg))
    print("History:", json.dumps(history, indent=2, ensure_ascii=False))
    print("Preferences:", json.dumps(preferences, indent=2, ensure_ascii=False))

    # Step 1: Preference collection (robust pattern)
    # Find the first pending preference
    pending = None
    for key, question in PREFERENCE_QUESTIONS:
        if not preferences.get(key):
            pending = key
            break

    # Always assign user's answer to the current pending key (if any)
    if user_msg and pending is not None and history and history[-1]["sender"] == "bot":
        preferences[pending] = user_msg

    # Now check if there’s another pending preference
    for k, q in PREFERENCE_QUESTIONS:
        if not preferences.get(k):
            bot_reply = q
            history.append({"sender": "bot", "text": bot_reply})
            print("Backend returned preferences:", json.dumps(preferences, indent=2, ensure_ascii=False), flush=True)
            return {
                "reply": bot_reply,
                "history": history,
                "preferences": preferences,
                "pending_preference": k
            }
    # If all preferences are filled, continue to news logic below

    # Step 2: All preferences collected, process as news query
    try:
        topics = preferences.get("topics", "technology")
        N = 5  # Only get top 5 articles

        cache_key = make_cache_key(topics, preferences)
        if cache_key in news_cache:
            summaries, format_pref = news_cache[cache_key]
        else:
            search_query = generate_search_query(f"{user_msg or topics}")
            one_week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            search_response = exa_search(
                search_query,
                start_published_date=one_week_ago,
                num_results=N,
                api_key=EXA_API_KEY
            )

            results = search_response.get("results", [])
            summaries = []
            summary_tasks = []
            contents_by_url = {}  # <-- always define before use!

            if not results:
                summaries = [{"title": "No Results", "url": "", "summary": "Sorry, I couldn't find any recent news articles for your query."}]
            else:
                urls = [item.get("url") for item in results if "url" in item]
                content_results = exa_get_contents(urls, EXA_API_KEY)
                contents_by_url = {item.get("url"): item for item in content_results}

                for item in results:
                    url = item.get("url", "")
                    title = item.get("title", "")
                    snippet = item.get("snippet", "").strip()
                    content = contents_by_url.get(url, {})
                    article_text = content.get("text", "").strip()

                    print(f"\n==== {title} ({url}) ====")
                    print(f"Article text length: {len(article_text)}")
                    print(f"Article text preview: {article_text[:150]}\n")

                    if article_text and len(article_text) >= 120:
                        summary_tasks.append(summarize_article_async(article_text, preferences))
                        summaries.append({"title": title, "url": url, "summary": None})
                    elif snippet and len(snippet) > 50:
                        summaries.append({"title": title, "url": url, "summary": f"(Preview) {snippet}"})
                    else:
                        summaries.append({"title": title, "url": url, "summary": "No readable article content available."})

                if summary_tasks:
                    openai_summaries = await asyncio.gather(*summary_tasks)
                    ai_idx = 0
                    for idx in range(len(summaries)):
                        if summaries[idx]["summary"] is None:
                            summaries[idx]["summary"] = openai_summaries[ai_idx]
                            ai_idx += 1

            format_pref = preferences.get("format", "paragraphs").lower()
            news_cache[cache_key] = (summaries, format_pref)

    except Exception as e:
        summaries = [{"title": "Error", "url": "", "summary": f"Sorry, an error occurred while processing your request: {str(e)[:120]}"}]
        format_pref = "paragraphs"

    history.append({"sender": "bot", "text": ""})  # Optional: leave reply blank if rendering summaries on frontend

    return {
        "reply": "",  # Optional: deprecated for summary display
        "summaries": summaries,
        "format": format_pref,
        "history": history,
        "preferences": preferences,
        "pending_preference": None
    }