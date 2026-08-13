const messagesEl = document.getElementById("messages");
const composeEl = document.getElementById("compose");
const usernameEl = document.getElementById("username");
const textEl = document.getElementById("text");
const sendBtn = document.getElementById("send");
const statusEl = document.getElementById("status");

const API_MESSAGES = "/api/messages";
const POLL_MS = 2000;

const savedName = localStorage.getItem("chat.username") || "";
usernameEl.value = savedName;

let lastCount = 0;
let firstLoad = true;

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.classList.remove("chat__status--online", "chat__status--offline");
  if (cls) statusEl.classList.add(cls);
}

function appendMessage(message, own) {
  const div = document.createElement("div");
  div.className = "message" + (own ? " message--own" : "");

  const time = new Date((message.ts || Date.now()) * 1000).toLocaleTimeString();
  const meta = document.createElement("span");
  meta.className = "message__meta";
  meta.textContent = `${message.username || "anonymous"} · ${time}`;

  const text = document.createElement("span");
  text.className = "message__text";
  text.textContent = message.text || "";

  div.appendChild(meta);
  div.appendChild(text);
  messagesEl.appendChild(div);
}

function render(messages) {
  for (const message of messages) {
    if (!message || message.id === undefined) continue;
    const own = message.username === usernameEl.value.trim();
    appendMessage(message, own);
  }
}

async function poll() {
  try {
    const resp = await fetch(API_MESSAGES);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const messages = data.messages || [];

    if (messages.length !== lastCount) {
      const start = firstLoad ? 0 : lastCount;
      render(messages.slice(start));
      lastCount = messages.length;
      firstLoad = false;
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
    setStatus(firstLoad ? "connecting…" : "online", "chat__status--online");
  } catch (err) {
    setStatus("backend offline", "chat__status--offline");
    console.error("poll failed:", err);
  }
}

async function sendMessage(event) {
  event.preventDefault();
  const username = usernameEl.value.trim();
  const text = textEl.value.trim();
  if (!username || !text) return;

  sendBtn.disabled = true;
  try {
    const resp = await fetch(API_MESSAGES, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, text }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    textEl.value = "";
    localStorage.setItem("chat.username", username);
    await poll();
  } catch (err) {
    setStatus("send failed", "chat__status--offline");
    console.error("send failed:", err);
  } finally {
    sendBtn.disabled = false;
    textEl.focus();
  }
}

composeEl.addEventListener("submit", sendMessage);
poll();
setInterval(poll, POLL_MS);
