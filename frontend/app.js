const messagesEl = document.getElementById("messages");
const composeEl = document.getElementById("compose");
const usernameEl = document.getElementById("username");
const textEl = document.getElementById("text");
const fileEl = document.getElementById("file");
const attachBtn = document.getElementById("attach");
const sendBtn = document.getElementById("send");
const clearBtn = document.getElementById("clear");
const statusEl = document.getElementById("status");

const API_MESSAGES = "/api/messages";
const API_UPLOAD = "/api/upload";
const POLL_MS = 2000;
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

const savedName = localStorage.getItem("chat.username") || "";
usernameEl.value = savedName;

let lastCount = 0;
let firstLoad = true;
let pendingFile = null;

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

  if (message.attachment) {
    const media = message.attachment.type === "video"
      ? createVideo(message.attachment)
      : createImage(message.attachment);
    div.appendChild(media);
  }

  if (text.textContent) {
    div.appendChild(text);
  }
  messagesEl.appendChild(div);
}

function createImage(attachment) {
  const img = document.createElement("img");
  img.className = "message__media";
  img.src = attachment.url;
  img.alt = attachment.name || "image";
  img.loading = "lazy";
  return img;
}

function createVideo(attachment) {
  const video = document.createElement("video");
  video.className = "message__media";
  video.src = attachment.url;
  video.controls = true;
  video.preload = "metadata";
  return video;
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

async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(API_UPLOAD, { method: "POST", body: form });
  if (!resp.ok) throw new Error(`upload failed: HTTP ${resp.status}`);
  return resp.json();
}

function clearAttachment() {
  pendingFile = null;
  fileEl.value = "";
  attachBtn.textContent = "+";
  attachBtn.classList.remove("chat__attach--pending");
  attachBtn.title = "Attach image/video";
}

attachBtn.addEventListener("click", () => fileEl.click());

fileEl.addEventListener("change", () => {
  const file = fileEl.files && fileEl.files[0];
  if (!file) {
    clearAttachment();
    return;
  }
  if (!file.type.startsWith("image/") && !file.type.startsWith("video/")) {
    setStatus("only image/video allowed", "chat__status--offline");
    clearAttachment();
    return;
  }
  if (file.size > MAX_FILE_SIZE) {
    setStatus("file too large (max 10 MB)", "chat__status--offline");
    clearAttachment();
    return;
  }
  pendingFile = file;
  attachBtn.textContent = "📎";
  attachBtn.classList.add("chat__attach--pending");
  attachBtn.title = `${file.name} (${(file.size / 1024).toFixed(0)} KB)`;
});

async function sendMessage(event) {
  event.preventDefault();
  const username = usernameEl.value.trim();
  const text = textEl.value.trim();
  if (!username || (!text && !pendingFile)) return;

  sendBtn.disabled = true;
  try {
    const body = { username, text };
    if (pendingFile) {
      const info = await uploadFile(pendingFile);
      body.attachment = {
        type: info.type,
        url: info.url,
        name: info.name || pendingFile.name,
      };
    }
    const resp = await fetch(API_MESSAGES, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    textEl.value = "";
    localStorage.setItem("chat.username", username);
    clearAttachment();
    await poll();
  } catch (err) {
    setStatus("send failed", "chat__status--offline");
    console.error("send failed:", err);
  } finally {
    sendBtn.disabled = false;
    textEl.focus();
  }
}

async function clearChat() {
  const confirmed = window.confirm("Delete all chats? This cannot be undone.");
  if (!confirmed) return;

  clearBtn.disabled = true;
  try {
    const resp = await fetch(API_MESSAGES, { method: "DELETE" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    messagesEl.innerHTML = "";
    lastCount = 0;
    firstLoad = true;
    setStatus("chat cleared", "chat__status--online");
  } catch (err) {
    setStatus("delete failed", "chat__status--offline");
    console.error("delete failed:", err);
  } finally {
    clearBtn.disabled = false;
  }
}

composeEl.addEventListener("submit", sendMessage);
clearBtn.addEventListener("click", clearChat);
poll();
setInterval(poll, POLL_MS);
