from __future__ import annotations


class ControlLoginFrontdoorService:
    """Own the operator control login surface outside the HTTP transport shell."""

    @staticmethod
    def render_html() -> str:
        return CONTROL_LOGIN_HTML


CONTROL_LOGIN_HTML = """<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>NYO AI Systems Control Login</title>
    <link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css\" rel=\"stylesheet\" integrity=\"sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH\" crossorigin=\"anonymous\">
    <style>
        :root { --ink:#1f1d19; --bg:#f3efe6; --panel:#fffdf8; --line:#d9ceba; --accent:#0f7a5c; --danger:#a82720; }
        body {
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            font-family: "Space Grotesk", "Segoe UI", sans-serif;
            color: var(--ink);
            background: radial-gradient(1000px 400px at 10% -20%, #d9ead7, transparent 60%), linear-gradient(160deg, #edf4ec, var(--bg));
        }
        .login-card {
            width: min(480px, 92vw);
            border: 1px solid var(--line);
            border-radius: 14px;
            background: var(--panel);
            box-shadow: 0 14px 30px rgba(0,0,0,0.08);
        }
        h1 { margin: 0 0 8px; font-size: 20px; }
        p { margin: 0 0 12px; color: #5f5a52; }
        .err { color: var(--danger); font-size: 13px; min-height: 18px; margin-top: 10px; }
        .btn-nova {
            color: #fff;
            font-weight: 700;
            border: 0;
            background: linear-gradient(135deg, var(--accent), #0a986f);
        }
    </style>
</head>
<body>
    <div class=\"login-card p-4\">
        <h1>NYO AI Systems Control Login</h1>
        <p>Sign in to access the branded operator console for the NYO runtime.</p>
        <form id=\"f\" class=\"d-grid gap-2\">
            <label for=\"u\" class=\"form-label mb-0\">Username</label>
            <input id=\"u\" class=\"form-control\" autocomplete=\"username\" />
            <label for=\"p\" class=\"form-label mb-0 mt-2\">Password</label>
            <input id=\"p\" class=\"form-control\" type=\"password\" autocomplete=\"current-password\" />
            <button type=\"submit\" class=\"btn btn-nova mt-3\">Sign In</button>
            <div class=\"err\" id=\"err\"></div>
        </form>
    </div>
    <script>
        const f = document.getElementById('f');
        const err = document.getElementById('err');
        f.addEventListener('submit', async (e) => {
            e.preventDefault();
            err.textContent = '';
            try {
                const r = await fetch('/api/control/login', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({
                        username: document.getElementById('u').value.trim(),
                        password: document.getElementById('p').value
                    })
                });
                const j = await r.json();
                if (!r.ok || !j.ok) throw new Error(j.error || 'login_failed');
                window.location.href = '/control';
            } catch (e) {
                err.textContent = 'Login failed: ' + e.message;
            }
        });
    </script>
</body>
</html>
"""


CONTROL_LOGIN_FRONTDOOR_SERVICE = ControlLoginFrontdoorService()
