"""App UI HTML templates for MCP Apps (e.g. Goodreads book list)."""

_SHARED_APP_SCRIPT = r"""
    (function () {
      const loading = document.getElementById("loading");
      const signinView = document.getElementById("signin");
      const successView = document.getElementById("success");
      const errorEl = document.getElementById("error");

      function show(view) {
        [loading, signinView, successView, errorEl].forEach(function (el) {
          el.classList.toggle("active", el === view);
        });
      }

      function escapeHtml(s) {
        if (typeof s !== "string") return "";
        const div = document.createElement("div");
        div.textContent = s;
        return div.innerHTML;
      }

      function onToolResult(result) {
        let data = null;
        const textPart = result.content && result.content.find(function (c) { return c.type === "text"; });
        const text = textPart && textPart.text;
        const structuredContent = result.structuredContent;
        if (text) {
          try { data = JSON.parse(text); } catch (_) {}
        }
        if (!data && structuredContent && typeof structuredContent === "object") {
          data = structuredContent;
        }
        if (!data) {
          errorEl.textContent = "No data received";
          show(errorEl);
          return;
        }
        if (data.signin_id != null || data.url) {
          const url = data.url || "#";
          signinView.innerHTML = "<p>Sign in to continue.</p><iframe class=\"signin-iframe\" src=\"" + escapeHtml(url) + "\" sandbox=\"allow-same-origin allow-forms allow-scripts allow-popups\" title=\"Sign in\"></iframe>";
          show(signinView);
          return;
        }
        if (successView) show(successView);
      }

      let nextId = 1;
      function sendRequest(method, params) {
        const id = nextId++;
        window.parent.postMessage({ jsonrpc: "2.0", id: id, method: method, params: params || {} }, "*");
        return new Promise(function (resolve, reject) {
          function listener(event) {
            const d = event.data;
            if (d && d.id === id) {
              window.removeEventListener("message", listener);
              if (d.result) resolve(d.result);
              else if (d.error) reject(new Error(d.error.message || "Request failed"));
            }
          }
          window.addEventListener("message", listener);
        });
      }

      function applyTheme(theme) {
        const value = (theme === "dark" || theme === "light") ? theme : "";
        if (value) document.documentElement.setAttribute("data-theme", value);
      }

      window.addEventListener("message", function (event) {
        const d = event.data;
        if (d && d.method === "ui/notifications/tool-result" && d.params) {
          onToolResult(d.params);
        }
        if (d && d.method === "ui/notifications/host-context-changed" && d.params) {
          const theme = d.params.theme || d.params.colorScheme;
          if (theme != null) applyTheme(String(theme).toLowerCase());
        }
      });

      sendRequest("ui/initialize", {
        appInfo: { name: "GetGather MCP App", version: "0.0.1" },
        appCapabilities: {},
        clientInfo: { name: "GetGather MCP Client", version: "0.0.1" },
        protocolVersion: "2024-11-05"
      }).then(function (result) {
        if (result && (result.hostContext || result.theme != null)) {
          const theme = (result.hostContext && result.hostContext.theme) || result.theme;
          if (theme != null) applyTheme(String(theme).toLowerCase());
        }
      }).catch(function () {});
    })();
"""


def render_app_ui_html(title: str = "MCP GetGather App") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --color-bg: #fff;
      --color-text: #1a1a1a;
      --color-card-bg: #fff;
      --color-border: #e5e5e5;
      --color-muted: #666;
      --color-muted-secondary: #999;
      --color-accent: #0066cc;
      --color-error: #c00;
      --shadow-card: 0 1px 3px rgba(0,0,0,0.06);
      --shadow-card-hover: 0 4px 12px rgba(0,0,0,0.1);
      --cover-bg: #f0f0f0;
      --cover-placeholder-start: #e8e8e8;
      --cover-placeholder-end: #d4d4d4;
    }}
    [data-theme="dark"] {{
      --color-bg: #1a1a1a;
      --color-text: #e5e5e5;
      --color-card-bg: #2d2d2d;
      --color-border: #444;
      --color-muted: #b0b0b0;
      --color-muted-secondary: #888;
      --color-accent: #6eb3f7;
      --color-error: #f66;
      --shadow-card: 0 1px 3px rgba(0,0,0,0.3);
      --shadow-card-hover: 0 4px 12px rgba(0,0,0,0.4);
      --cover-bg: #333;
      --cover-placeholder-start: #404040;
      --cover-placeholder-end: #363636;
    }}
    @media (prefers-color-scheme: dark) {{
      :root:not([data-theme="light"]) {{
        --color-bg: #1a1a1a;
        --color-text: #e5e5e5;
        --color-card-bg: #2d2d2d;
        --color-border: #444;
        --color-muted: #b0b0b0;
        --color-muted-secondary: #888;
        --color-accent: #6eb3f7;
        --color-error: #f66;
        --shadow-card: 0 1px 3px rgba(0,0,0,0.3);
        --shadow-card-hover: 0 4px 12px rgba(0,0,0,0.4);
        --cover-bg: #333;
        --cover-placeholder-start: #404040;
        --cover-placeholder-end: #363636;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; padding: 1rem; font-family: system-ui, -apple-system, sans-serif; font-size: 14px; background: var(--color-bg); color: var(--color-text); }}
    .view {{ display: none; }}
    .view.active {{ display: block; }}
    #signin a {{ color: var(--color-accent); }}
    #signin .signin-iframe {{ width: 100%; min-height: 480px; border: 1px solid var(--color-border); border-radius: 8px; margin-top: 0.5rem; }}
    #error {{ color: var(--color-error); }}
    .app-ui-success-message {{ color: var(--color-muted); margin: 0; }}
    #loading.view {{ display: none; }}
    #loading.view.active {{
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 120px;
      gap: 1rem;
    }}
    .loading-spinner {{
      width: 28px;
      height: 28px;
      border: 3px solid var(--color-border);
      border-top-color: var(--color-accent);
      border-radius: 50%;
      animation: loading-spin 0.7s linear infinite;
    }}
    .loading-text {{
      font-size: 0.875rem;
      color: var(--color-muted);
    }}
    @keyframes loading-spin {{
      to {{ transform: rotate(360deg); }}
    }}
  </style>
</head>
<body>
  <div id="loading" class="view active">
    <div class="loading-spinner" aria-hidden="true"></div>
    <span class="loading-text">Loading…</span>
  </div>
  <div id="signin" class="view"></div>
  <div id="success" class="view"><p class="app-ui-success-message">You're signed in. Data has been loaded.</p></div>
  <div id="error" class="view"></div>
  <script>{_SHARED_APP_SCRIPT}</script>
</body>
</html>"""
