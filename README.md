# AI News Chat Demo

An AI-powered chat app that collects user preferences, optimizes search queries, and summarizes news articles in your preferred format (bullets or paragraphs).  
Built with a React (Next.js) frontend and FastAPI backend.

---

## Features

- Interactive preference collection (tone, format, language, style, topics)
- AI-powered search query generation and article summarization
- Simple chat UI with Reset button to clear client-side state (input, chat history, preferences). The backend is stateless by design.

---

### Project Structure
ai-news-chat-demo/
  ├── backend/           # FastAPI backend (main.py, requirements.txt, Dockerfile, .env)
  ├── src/app/           # React/Next.js frontend
  ├── package.json
  ├── README.md
  └── ...

---

## Local Deployment Instructions

### 1. Clone my repository
```bash
git clone https://github.com/eugenewoo/ai-news-chat-demo.git
cd ai-news-chat-demo
```
### 2. Create .env file in /backend folder
```bash
OPENAI_API_KEY=your_openai_api_key
EXA_API_KEY=your_exa_api_key
```
### 3. Set up the Python Backend via Docker container
```bash
cd backend
docker build -t ai-news-backend .
docker run --env-file .env -p 8000:8000 ai-news-backend
```
The backend API is now running at http://localhost:8000/chatbot.

### 4. Set up the React/Next.js frontend
```bash
npm install
npm run dev
```
The frontend is now available at http://localhost:3000.

---

## Assumptions & Decisions
- **Preferences Flow:** Preferences are collected in order using PREFERENCE_QUESTIONS. Backend indicates which preferences remain unset.
- **Demo Scope:** Non-production grade i.e. no authentication, database, or security management 
- **API Keys:** You must supply your own OpenAI and Exa API keys in the backend .env.
- **Choice of LLM:** ChatGPT-3.5-Turbo instead of 4o for optimal balance of speed and performance 
- **Localhost only:** Communication is via localhost for dev; CORS must be configured if deploying.
- **No use of LangChain, LangGraph, or similar frameworks:** All LLM, prompt, and workflow logic is written directly in Python without any orchestration, agentic, or workflow frameworks.
- **No SDKs or abstractions:** All external API requests (OpenAI, Exa, etc.) are made via direct HTTP requests (using the `requests` library) and not with SDKs, wrappers, or higher-level abstractions.

## Future Improvements given more time
1. I was unable to consistently display the news summary in bullet or paragraph format, despite extensive attempts to resolve this in both the backend and frontend.
2. The final preference item does not update to a tick until the news summary appears. I have dedicated significant time to addressing this issue (see the preferences data logging in main.py), but a reliable solution remains elusive.
