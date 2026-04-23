import tempfile
import unittest
from pathlib import Path

from services.control_assets import CONTROL_ASSETS_SERVICE


class TestControlAssetsService(unittest.TestCase):
    def test_render_control_html_replaces_asset_tokens(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            template = root / "control.html"
            css = root / "control.css"
            js = root / "control.js"
            template.write_text(
                '<link href="/static/control.css?v={{CONTROL_CSS_VERSION}}"><script src="/static/control.js?v={{CONTROL_JS_VERSION}}"></script>',
                encoding="utf-8",
            )
            css.write_text("body{}", encoding="utf-8")
            js.write_text("console.log('ok')", encoding="utf-8")

            html = CONTROL_ASSETS_SERVICE.render_control_html(template, css, js)

        self.assertRegex(html, r"control\.css\?v=[0-9a-f]{12}")
        self.assertRegex(html, r"control\.js\?v=[0-9a-f]{12}")
        self.assertNotIn("{{CONTROL_CSS_VERSION}}", html)
        self.assertNotIn("{{CONTROL_JS_VERSION}}", html)

    def test_read_asset_text_returns_missing_asset_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "missing.html"
            html = CONTROL_ASSETS_SERVICE.read_asset_text(missing)

        self.assertIn("Missing asset: missing.html", html)


if __name__ == "__main__":
    unittest.main()