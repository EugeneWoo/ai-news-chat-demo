# main.py - FastAPI backend for AI News Chat. Handles preference collection, Exa/LLM integration, and summarization.
# =====================
# Section: Imports and Environment Setup
# =====================
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()
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

# =====================
# Section: Pydantic Models
# =====================
class ChatInput(BaseModel):
    message: str
    history: list
    preferences: dict

# =====================
# Section: Preference Questions and Constants
# =====================
PREFERENCE_QUESTIONS = [
    ("tone", "What is your preferred tone of voice? (e.g., formal, casual, enthusiastic)"),
    ("format", "What is your preferred response format? (e.g., bullet points, paragraphs)"),
    ("language", "What is your language preference? (e.g., English, Spanish)"),
    ("style", "What interaction style do you prefer? (e.g., concise, detailed)"),
    ("topics", "What are your preferred news topics? (e.g., technology, sports, politics)"),
]

# =====================
# Section: OpenAI Tool Schemas
# =====================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "news_fetcher",
            "description": "Fetches the latest news articles on a given topic using the Exa API",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The news topic to search for (e.g., 'technology', 'sports', 'politics')"
                    }
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "news_summarizer",
            "description": "Summarizes a news article based on user preferences",
            "parameters": {
                "type": "object",
                "properties": {
                    "article_text": {
                        "type": "string",
                        "description": "The full text content of the article to summarize"
                    },
                    "preferences": {
                        "type": "object",
                        "description": "User preferences for tone, style, language, and format"
                    }
                },
                "required": ["article_text", "preferences"]
            }
        }
    }
]

# =====================
# Section: In-Memory Cache
# =====================
# Simple in-memory cache
news_cache: dict = {}

# =====================
# Section: Utility Functions
# =====================
def make_cache_key(topic, preferences):
    # Use a tuple of topic + frozen preferences dict as the cache key
    key = (topic.strip().lower(), tuple(sorted((k, str(v).strip().lower()) for k, v in preferences.items())))
    return key

# ---- Generate Search Query using LLM ----
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

# ---- Summarize Article using LLM ----
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

# ---- Exa API: News Search ----
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

# ---- Exa API: Get Article Contents ----
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

# =====================
# Section: Tool Wrapper Functions
# =====================
async def news_fetcher(topic: str, preferences: dict | None = None) -> list:
    """
    Tool wrapper for fetching news articles on a given topic.
    Returns a list of articles with title, url, and text content.
    Includes caching to avoid redundant API calls.
    """
    try:
        # Check cache first
        if preferences is None:
            preferences = {}
        cache_key = make_cache_key(topic, preferences)
        
        if cache_key in news_cache:
            print(f"Cache hit for topic: {topic}")
            cached_articles, _ = news_cache[cache_key]
            # Convert cached summaries back to articles format
            articles = []
            for item in cached_articles:
                articles.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "text": item.get("summary", "")  # Use summary as text for consistency
                })
            return articles
        
        print(f"Cache miss for topic: {topic}, fetching fresh data...")
        
        N = 5  # Fetch top 5 articles
        search_query = generate_search_query(topic)
        one_week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        search_response = exa_search(
            search_query,
            start_published_date=one_week_ago,
            num_results=N,
            api_key=EXA_API_KEY
        )
        
        results = search_response.get("results", [])
        if not results:
            articles = [{"title": "No Results", "url": "", "text": "Sorry, I couldn't find any recent news articles for your query."}]
            # Cache the empty result
            news_cache[cache_key] = (articles, preferences.get("format", "paragraphs"))
            return articles
        
        # Get full article contents
        urls = [item.get("url") for item in results if "url" in item]
        content_results = exa_get_contents(urls, EXA_API_KEY)
        contents_by_url = {item.get("url"): item for item in content_results}
        
        articles = []
        for item in results:
            url = item.get("url", "")
            title = item.get("title", "")
            snippet = item.get("snippet", "").strip()
            content = contents_by_url.get(url, {})
            article_text = content.get("text", "").strip()
            
            # Use full article text if available, otherwise use snippet
            if article_text and len(article_text) >= 120:
                text_content = article_text
            elif snippet and len(snippet) > 50:
                text_content = f"(Preview) {snippet}"
            else:
                text_content = "No readable article content available."
            
            articles.append({
                "title": title,
                "url": url,
                "text": text_content
            })
        
        return articles
        
    except Exception as e:
        return [{"title": "Error", "url": "", "text": f"Sorry, an error occurred while fetching news: {str(e)[:120]}"}]

async def news_summarizer(article_text: str, preferences: dict) -> str:
    """
    Tool wrapper for summarizing news articles based on user preferences.
    """
    try:
        summary = await summarize_article_async(article_text, preferences)
        return summary
    except Exception as e:
        return f"Error summarizing article: {str(e)[:120]}"

# =====================
# Section: OpenAI Tool Calling Logic
# =====================
def build_conversation_context(history: list, preferences: dict, user_msg: str) -> list:
    """
    Build the conversation context for OpenAI, including system message and history.
    """
    # Create system message with user preferences
    pref_text = ""
    if preferences:
        pref_parts = []
        for key, value in preferences.items():
            pref_parts.append(f"{key}: {value}")
        pref_text = f"User preferences: {', '.join(pref_parts)}"
    
    system_message = f"""You are an AI news agent that helps users stay informed about current events. 
{pref_text}

You have access to two tools:
1. news_fetcher: Fetches recent news articles on a given topic
2. news_summarizer: Summarizes article content based on user preferences

Use these tools when users ask about news or current events. Always respect the user's preferences for tone, style, language, and format when responding."""

    messages = [{"role": "system", "content": system_message}]
    
    # Add conversation history
    for msg in history:
        if msg["sender"] == "user":
            messages.append({"role": "user", "content": msg["text"]})
        elif msg["sender"] == "bot" and msg["text"]:  # Skip empty bot messages
            messages.append({"role": "assistant", "content": msg["text"]})
    
    # Add current user message
    if user_msg:
        messages.append({"role": "user", "content": user_msg})
    
    return messages

async def openai_tool_calling_loop(messages: list, preferences: dict) -> dict:
    """
    Handle the OpenAI tool calling loop - call OpenAI, execute tools, repeat until final response.
    """
    max_iterations = 10  # Prevent infinite loops
    iteration = 0
    summaries: list = []
    
    while iteration < max_iterations:
        iteration += 1
        print(f"\n=== OpenAI Tool Calling Loop - Iteration {iteration} ===")
        
        # Call OpenAI with tools
        response = await asyncio.to_thread(
            openai.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=500,
            temperature=0.7
        )
        
        message = response.choices[0].message
        print(f"OpenAI response type: {message.content is not None}, tool_calls: {message.tool_calls is not None}")
        
        # If no tool calls, we have the final response
        if not message.tool_calls:
            return {
                "text": message.content or "",
                "summaries": summaries
            }
        
        # Add assistant message to conversation
        messages.append({
            "role": "assistant", 
            "content": message.content,
            "tool_calls": [tc.dict() for tc in message.tool_calls] if message.tool_calls else None
        })
        
        # Execute tool calls
        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            print(f"Executing tool: {function_name} with args: {function_args}")
            
            if function_name == "news_fetcher":
                topic = function_args.get("topic", "")
                articles = await news_fetcher(topic, preferences)
                
                # Check if we need to process summaries or if they're cached
                cache_key = make_cache_key(topic, preferences)
                if cache_key in news_cache:
                    # Use cached summaries
                    cached_summaries, _ = news_cache[cache_key]
                    summaries.extend(cached_summaries)
                else:
                    # Process articles for summaries and create proper format for frontend
                    processed_summaries = []
                    for article in articles:
                        if article.get("text") and len(article["text"]) > 120 and not article["text"].startswith("(Preview)"):
                            # Summarize the article
                            summary_text = await news_summarizer(article["text"], preferences)
                            processed_summaries.append({
                                "title": article.get("title", ""),
                                "url": article.get("url", ""),
                                "summary": summary_text
                            })
                        else:
                            # Use the text as-is (for previews or short content)
                            processed_summaries.append({
                                "title": article.get("title", ""),
                                "url": article.get("url", ""),
                                "summary": article.get("text", "No content available")
                            })
                    
                    # Cache the processed summaries
                    format_pref = preferences.get("format", "paragraphs").lower()
                    news_cache[cache_key] = (processed_summaries, format_pref)
                    
                    # Store summaries for final response
                    summaries.extend(processed_summaries)
                
                # Add simplified tool result to conversation for OpenAI
                tool_result = f"Found {len(articles)} articles on topic '{topic}'"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result
                })
                
            elif function_name == "news_summarizer":
                article_text = function_args.get("article_text", "")
                prefs = function_args.get("preferences", preferences)
                
                summary = await news_summarizer(article_text, prefs)
                
                # Add tool result to conversation
                messages.append({
                    "role": "tool", 
                    "tool_call_id": tool_call.id,
                    "content": summary
                })
                
            else:
                # Unknown tool
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id, 
                    "content": f"Error: Unknown tool {function_name}"
                })
    
    # If we hit max iterations, return what we have
    return {
        "text": "I apologize, but I encountered an issue processing your request.",
        "summaries": summaries
    }

# =====================
# Section: FastAPI Endpoints
# =====================
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

    # Step 2: All preferences collected, use OpenAI tool calling
    try:
        # Build conversation context for OpenAI
        messages = build_conversation_context(history, preferences, user_msg)
        
        # Call OpenAI with tool schemas - this will handle the tool calling loop
        final_response = await openai_tool_calling_loop(messages, preferences)
        
        # Extract summaries from the final response if present
        summaries = final_response.get("summaries", [])
        format_pref = preferences.get("format", "paragraphs").lower()
        
        return {
            "reply": final_response.get("text", ""),
            "summaries": summaries,
            "format": format_pref,
            "history": history,
            "preferences": preferences,
            "pending_preference": None
        }
        
    except Exception as e:
        print(f"Error in chatbot endpoint: {str(e)}")
        return {
            "reply": f"Sorry, an error occurred: {str(e)[:120]}",
            "summaries": [],
            "format": "paragraphs",
            "history": history,
            "preferences": preferences,
            "pending_preference": None
        }