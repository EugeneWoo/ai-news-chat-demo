// Main chat page for AI News Agent web app. Handles preference collection, chat UI, and backend communication.
"use client";
import React, { useState, useEffect, useRef, FormEvent } from "react";

// =====================
// Section: Type Definitions & Constants
// =====================
type Summary = {
  title: string;
  url: string;
  summary: string;
};

type Message = {
  sender: "bot" | "user";
  text: string;
  summaries?: Summary[]; // for news summaries
  format?: string; // for formatting preference (bullet points, paragraphs)
};

const PREFERENCE_QUESTIONS = [
  { key: "tone", question: "What is your preferred tone of voice? (e.g., formal, casual, enthusiastic)" },
  { key: "format", question: "What is your preferred response format? (e.g., bullet points, paragraphs)" },
  { key: "language", question: "What is your language preference? (e.g., English, Spanish)" },
  { key: "style", question: "What interaction style do you prefer? (e.g., concise, detailed)" },
  { key: "topics", question: "What are your preferred news topics? (e.g., technology, sports, politics)" }
];

const PREFERENCE_KEYS = [
  { key: "tone", label: "Tone of Voice" },
  { key: "format", label: "Response Format" },
  { key: "language", label: "Language" },
  { key: "style", label: "Interaction Style" },
  { key: "topics", label: "Preferred News Topics" },
];

type Preferences = {
  [key: string]: string;
};

// =====================
// Section: Home Component
// =====================
export default function Home() {
  // State Declarations
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<Message[]>([
    { sender: "bot", text: PREFERENCE_QUESTIONS[0].question }
  ]);
  const [preferences, setPreferences] = useState<Preferences>({});
  const [pendingPrefIndex, setPendingPrefIndex] = useState(0);
  const [allPrefsSet, setAllPrefsSet] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const chatBoxRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when history updates
  useEffect(() => {
    if (chatBoxRef.current) {
      chatBoxRef.current.scrollTop = chatBoxRef.current.scrollHeight;
    }
  }, [history]);

  // Form Submit Handler: handleSend
  async function handleSend(e: FormEvent) {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    setIsLoading(true);

    const newHistory = [...history, { sender: "user", text: input }];
    let newPrefs = { ...preferences };

    // Preference collection logic
    if (!allPrefsSet) {
      const prefKey = PREFERENCE_QUESTIONS[pendingPrefIndex].key;
      newPrefs[prefKey] = input;
    }

    setInput("");
    setHistory(newHistory);

    try {
      const res = await fetch("http://localhost:8000/chatbot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: input,
          history: newHistory,
          preferences: newPrefs,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Sorry, there was a problem connecting to the backend.");
      }

      // Create bot message with summaries and format
      const botMsg: Message = {
        sender: "bot",
        text: data.reply || "",
        summaries: data.summaries || [],
        format: data.format
      };

      setHistory([...newHistory, botMsg]);
      console.log('Backend returned preferences:', data.preferences);
      setPreferences(data.preferences);
      console.log('[UI] Preferences state after update:', data.preferences);

      // Figure out which preference is next or if all are set
      if (data.pending_preference) {
        setPendingPrefIndex(
          PREFERENCE_QUESTIONS.findIndex(q => q.key === data.pending_preference)
        );
        setAllPrefsSet(false);
      } else {
        setAllPrefsSet(true);
      }
    } catch (err) {
      setHistory([
        ...newHistory,
        { sender: "bot", text: "Sorry, there was a problem connecting to the backend." }
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  // Preferences and History Reset: handleReset
  function handleReset() {
    setInput("");
    setPreferences({});
    setPendingPrefIndex(0);
    setAllPrefsSet(false);
    setHistory([{ sender: "bot", text: PREFERENCE_QUESTIONS[0].question }]);
  }

  // Render summaries component for a message
  const renderSummaries = (summaries: Summary[], format?: string) => {
    if (!summaries || summaries.length === 0) return null;

    if (format && format.includes("bullet")) {
      return (
        <ul style={{ marginTop: "8px", paddingLeft: "20px" }}>
          {summaries.map((s, i) => (
            <li key={i} style={{ marginBottom: "8px" }}>
              {s.url ? (
                <b>
                  <a href={s.url} target="_blank" rel="noopener noreferrer" style={{ color: "#0066cc" }}>
                    {s.title}
                  </a>
                </b>
              ) : (
                <b>{s.title}</b>
              )}
              {": "}
              {s.summary}
            </li>
          ))}
        </ul>
      );
    } else {
      // Default: paragraphs
      return (
        <div style={{ marginTop: "8px" }}>
          {summaries.map((s, i) => (
            <p key={i} style={{ marginBottom: "8px" }}>
              {s.url ? (
                <b>
                  <a href={s.url} target="_blank" rel="noopener noreferrer" style={{ color: "#0066cc" }}>
                    {s.title}
                  </a>
                </b>
              ) : (
                <b>{s.title}</b>
              )}
              {": "}
              {s.summary}
            </p>
          ))}
        </div>
      );
    }
  };

  // Unified Chat Display Renderer: renderChat
  const renderChat = () => {
    return (
      <>
        {history.map((msg, i) => (
          <div key={i} style={{ margin: "12px 0", padding: "8px", backgroundColor: msg.sender === "bot" ? "#f5f5f5" : "#e8f4fd", borderRadius: "6px" }}>
            <div>
              <b style={{ color: msg.sender === "bot" ? "#333" : "#0066cc" }}>
                {msg.sender === "bot" ? "Bot" : "You"}:
              </b> 
              {msg.text && <span style={{ marginLeft: "8px" }}>{msg.text}</span>}
            </div>
            {msg.sender === "bot" && renderSummaries(msg.summaries || [], msg.format)}
          </div>
        ))}
      </>
    );
  };

  // Main Component Render
  return (
    <div style={{ maxWidth: 600, margin: "2rem auto", fontFamily: "sans-serif" }}>
      <h2>AI News Agent Chat</h2>
      <PreferenceChecklist preferences={preferences} />
      <div 
        ref={chatBoxRef}
        style={{ 
          minHeight: 220, 
          maxHeight: 400, 
          overflowY: "auto", 
          border: "1px solid #ddd", 
          padding: 10, 
          margin: "10px 0", 
          borderRadius: 6 
        }}
      >
        {renderChat()}
        {isLoading && (
          <div style={{ margin: "12px 0", padding: "8px", backgroundColor: "#f5f5f5", borderRadius: "6px", textAlign: "center", color: "#666" }}>
            <i>AI is thinking...</i>
          </div>
        )}
      </div>
      <form onSubmit={handleSend} style={{ display: "flex", gap: 8 }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          disabled={isLoading}
          style={{ 
            flex: 1, 
            padding: 8, 
            borderRadius: 4, 
            border: "1px solid #bbb",
            opacity: isLoading ? 0.6 : 1
          }}
          placeholder="Type your message..."
        />
        <button 
          type="submit" 
          disabled={isLoading}
          style={{ 
            padding: "8px 18px",
            opacity: isLoading ? 0.6 : 1,
            cursor: isLoading ? "not-allowed" : "pointer"
          }}
        >
          {isLoading ? "Sending..." : "Send"}
        </button>
        <button
          type="button"
          style={{ padding: "8px 18px", background: "#eee", border: "1px solid #bbb", borderRadius: 4 }}
          onClick={handleReset}
        >
          Reset
        </button>
      </form>
      <div style={{ color: "#999", fontSize: 13, marginTop: 8 }}>
        (Powered by Exa AI and OpenAI. Backend at /chatbot.)
      </div>
    </div>
  );
}

// =====================
// Section: PreferenceChecklist Component
// =====================
function PreferenceChecklist({ preferences }: { preferences: Preferences }) {
  console.log("Checklist received preferences:", preferences);
  return (
    <div style={{ margin: "10px 0 12px 0" }}>
      <b>Preference Checklist:</b>
      <ul style={{ margin: "8px 0 0 14px", padding: 0 }}>
        {PREFERENCE_KEYS.map(pref => (
          <li key={pref.key}>
            {pref.label}: {preferences[pref.key] ? "✅" : "❌"}
          </li>
        ))}
      </ul>
    </div>
  );
}