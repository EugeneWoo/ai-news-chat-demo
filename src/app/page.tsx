"use client";
import React, { useState, useEffect, FormEvent } from "react";

type Message = {
  sender: "bot" | "user";
  text: string;
  data?: any; // for summaries/format when included by the backend
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

export default function Home() {
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<Message[]>([
    { sender: "bot", text: PREFERENCE_QUESTIONS[0].question }
  ]);
  const [preferences, setPreferences] = useState<Preferences>({});
  const [pendingPrefIndex, setPendingPrefIndex] = useState(0);
  const [allPrefsSet, setAllPrefsSet] = useState(false);

  // Send message to backend
  async function handleSend(e: FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;

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

      // Attach summaries/format to the bot message for display logic
      const botMsg: Message = {
        sender: "bot",
        text: data.reply || "",
        data: {
          summaries: data.summaries,
          format: data.format
        }
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
    }
  }

  function handleReset() {
    setInput("");
    setPreferences({});
    setPendingPrefIndex(0);
    setAllPrefsSet(false);
    setHistory([{ sender: "bot", text: PREFERENCE_QUESTIONS[0].question }]);
  }

  // Display summaries array as bullets or paragraphs, or fallback to legacy text
  const renderChat = () => {
    // Find latest bot message with summaries
    const lastBotMsgWithSummaries = [...history]
      .reverse()
      .find(msg => msg.sender === "bot" && msg.data && msg.data.summaries && msg.data.format);

    if (lastBotMsgWithSummaries && lastBotMsgWithSummaries.data) {
      const { summaries, format } = lastBotMsgWithSummaries.data;
      if (summaries && Array.isArray(summaries) && summaries.length > 0) {
        if (format && format.includes("bullet")) {
          return (
            <ul>
              {summaries.map((s: any, i: number) => (
                <li key={i}>
                  {s.url ? (
                    <b>
                      <a href={s.url} target="_blank" rel="noopener noreferrer">
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
            <div>
              {summaries.map((s: any, i: number) => (
                <p key={i}>
                  {s.url ? (
                    <b>
                      <a href={s.url} target="_blank" rel="noopener noreferrer">
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
      }
    }

    // Legacy fallback: show all messages as before
    return (
      <>
        {history.map((msg, i) => (
          <div key={i} style={{ margin: "12px 0" }}>
            <b>{msg.sender === "bot" ? "Bot" : "You"}:</b> {msg.text}
          </div>
        ))}
      </>
    );
  };

  return (
    <div style={{ maxWidth: 600, margin: "2rem auto", fontFamily: "sans-serif" }}>
      <h2>AI News Agent Chat</h2>
      <PreferenceChecklist preferences={preferences} />
      <div style={{ minHeight: 220, border: "1px solid #ddd", padding: 10, margin: "10px 0", borderRadius: 6 }}>
        {renderChat()}
      </div>
      <form onSubmit={handleSend} style={{ display: "flex", gap: 8 }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          style={{ flex: 1, padding: 8, borderRadius: 4, border: "1px solid #bbb" }}
          placeholder="Type your message..."
        />
        <button type="submit" style={{ padding: "8px 18px" }}>Send</button>
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