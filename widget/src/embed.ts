/**
 * Chatbase Replica Host Embed Loader
 * Reconstructs Chatbase embed.min.js architecture (Finding FIND-F01 & FIND-D01)
 */

interface RegisteredTools {
  [toolName: string]: (args: any, user: any) => Promise<any> | any;
}

interface UserIdentity {
  user_id?: string;
  user_hash?: string;
}

(function () {
  const currentScript = document.currentScript as HTMLScriptElement;
  const agentId = currentScript?.getAttribute("data-agent-id") || currentScript?.getAttribute("id") || (window as any).orbitAgentId || "";
  const backendUrl = currentScript?.getAttribute("data-backend-url") || "http://localhost:8000";

  let registeredTools: RegisteredTools = {};
  let currentUser: UserIdentity = {};
  let isOpen = false;

  // Global Chatbase command queue and dispatcher
  const chatbase = function (command: string, ...args: any[]) {
    switch (command) {
      case "registerTools":
        if (typeof args[0] === "object") {
          registeredTools = { ...registeredTools, ...args[0] };
        }
        break;
      case "identify":
        if (typeof args[0] === "object") {
          currentUser = { ...currentUser, ...args[0] };
          iframe.contentWindow?.postMessage({ type: "IDENTIFY_USER", user: currentUser }, backendUrl);
        }
        break;
      case "open":
        setChatOpen(true);
        break;
      case "close":
        setChatOpen(false);
        break;
      case "toggle":
        setChatOpen(!isOpen);
        break;
      default:
        console.warn("[Chatbase Replica] Unknown command:", command);
    }
  };

  (window as any).chatbase = chatbase;

  // 1. Inject Floating Bubble Button
  const button = document.createElement("button");
  button.id = "chatbase-bubble-button";
  button.setAttribute("aria-label", "Open Chat");
  Object.assign(button.style, {
    position: "fixed",
    bottom: "24px",
    right: "24px",
    width: "60px",
    height: "60px",
    borderRadius: "50%",
    backgroundColor: "#1e40af",
    color: "#ffffff",
    border: "none",
    boxShadow: "0 4px 14px rgba(0, 0, 0, 0.25)",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: "999998",
    transition: "transform 0.2s cubic-bezier(0.16, 1, 0.3, 1)"
  });

  button.innerHTML = `
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
    </svg>
  `;

  button.addEventListener("mouseenter", () => (button.style.transform = "scale(1.06)"));
  button.addEventListener("mouseleave", () => (button.style.transform = "scale(1)"));
  button.addEventListener("click", () => setChatOpen(!isOpen));

  // 2. Inject Sandboxed Iframe
  const iframe = document.createElement("iframe");
  iframe.id = "chatbase-iframe";
  iframe.src = `${backendUrl}/chatbot-iframe/${agentId}?backend=${encodeURIComponent(backendUrl)}`;
  Object.assign(iframe.style, {
    position: "fixed",
    bottom: "96px",
    right: "24px",
    width: "420px",
    height: "640px",
    maxWidth: "calc(100vw - 32px)",
    maxHeight: "calc(100vh - 120px)",
    border: "none",
    borderRadius: "16px",
    boxShadow: "0 12px 36px rgba(0, 0, 0, 0.22)",
    zIndex: "999999",
    display: "none",
    opacity: "0",
    transform: "translateY(16px)",
    transition: "all 0.25s cubic-bezier(0.16, 1, 0.3, 1)"
  });

  function setChatOpen(open: boolean) {
    isOpen = open;
    if (open) {
      iframe.style.display = "block";
      requestAnimationFrame(() => {
        iframe.style.opacity = "1";
        iframe.style.transform = "translateY(0)";
      });
      button.innerHTML = `
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      `;
    } else {
      iframe.style.opacity = "0";
      iframe.style.transform = "translateY(16px)";
      setTimeout(() => (iframe.style.display = "none"), 250);
      button.innerHTML = `
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
      `;
    }
  }

  // 3. Handle Cross-Document PostMessage RPC
  window.addEventListener("message", async (event) => {
    const data = event.data;
    if (event.source !== iframe.contentWindow || !data || typeof data !== "object") return;

    if (data.type === "WIDGET_ACTION_CALL") {
      const { toolName, toolCallId, input } = data;
      const fn = registeredTools[toolName];
      if (fn && typeof fn === "function") {
        try {
          const result = await fn(input, currentUser);
          iframe.contentWindow?.postMessage(
            { type: "TOOL_RESULT", toolCallId, output: result, status: "success" },
            backendUrl
          );
        } catch (err: any) {
          iframe.contentWindow?.postMessage(
            { type: "TOOL_RESULT", toolCallId, output: { error: err.message }, status: "error" },
            backendUrl
          );
        }
      } else {
        iframe.contentWindow?.postMessage(
          { type: "TOOL_RESULT", toolCallId, output: { error: `Tool ${toolName} not registered` }, status: "error" },
          backendUrl
        );
      }
    }
  });

  document.body.appendChild(button);
  document.body.appendChild(iframe);
})();
