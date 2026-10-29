import { createContext, useContext, useState } from "react";
import client from "../api/client";

// Shared AI Advisor conversation. Both presentations — the full
// /advisor page and the mini widget docked on the Portfolio page —
// read and write this same state, so the conversation is continuous
// when switching between them.

const WELCOME = {
  role: "assistant",
  text: "Hi! I'm your NoryvX AI Financial Advisor. I have access to your real account data — ask me anything about your spending, savings, investments, or balance.",
};

const AdvisorContext = createContext(null);

export function AdvisorProvider({ children }) {
  const [messages, setMessages] = useState([WELCOME]);
  // history sent to API: only role + content (no display-only "text" key)
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);

  async function send(message) {
    const text = message.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading(true);
    try {
      const res = await client.post("/api/advisor/chat", {
        message: text,
        history, // send previous turns so the LLM has context
      });
      const reply = res.data.response;
      setMessages((prev) => [...prev, { role: "assistant", text: reply }]);
      setHistory((prev) => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: reply },
      ]);
    } catch {
      setMessages((prev) => [...prev, {
        role: "assistant",
        text: "Sorry, I couldn't reach the server. Please try again.",
      }]);
    } finally {
      setLoading(false);
    }
  }

  function clearChat() {
    setMessages([{
      role: "assistant",
      text: "Chat cleared. What would you like to know?",
    }]);
    setHistory([]);
  }

  return (
    <AdvisorContext.Provider value={{ messages, loading, send, clearChat }}>
      {children}
    </AdvisorContext.Provider>
  );
}

export function useAdvisor() {
  return useContext(AdvisorContext);
}
