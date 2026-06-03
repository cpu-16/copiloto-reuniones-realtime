// Lee el token del query string (?token=...) que pasa el launcher.
const params = new URLSearchParams(location.search);
const token = params.get("token") || "";
const ws = new WebSocket(`ws://${location.host}/ws?token=${encodeURIComponent(token)}`);

const $status = document.getElementById("status");
const $transcript = document.getElementById("transcript");
const $suggestion = document.getElementById("suggestion");
const $ask = document.getElementById("ask");

ws.onopen = () => ($status.textContent = "conectado");
ws.onclose = () => ($status.textContent = "desconectado");

ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.type === "transcript.final") {
    const div = document.createElement("div");
    div.className = "line";
    div.textContent = m.text;
    $transcript.appendChild(div);
    $transcript.scrollTop = $transcript.scrollHeight;
  } else if (m.type === "suggestion") {
    $suggestion.classList.remove("empty");
    $suggestion.textContent = "💡 " + m.text;
  } else if (m.type === "status") {
    $status.textContent = m.state + (m.detail ? ` — ${m.detail}` : "");
  }
};

function send() {
  const text = $ask.value.trim();
  if (!text) return;
  ws.send(JSON.stringify({ type: "ask", text }));
  $ask.value = "";
}
document.getElementById("send").onclick = send;
$ask.addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
document.getElementById("clear").onclick = () => { $transcript.innerHTML = ""; };
