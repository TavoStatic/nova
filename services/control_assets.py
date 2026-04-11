from __future__ import annotations

import hashlib
from pathlib import Path


class ControlAssetsService:
    """Own control asset loading and cache-busting token generation outside HTTP transport."""

    @staticmethod
    def read_asset_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except Exception as exc:
            return f"<!doctype html><html><body><pre>Missing asset: {path.name}: {exc}</pre></body></html>"

    @staticmethod
    def asset_version_token(path: Path) -> str:
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        except Exception:
            try:
                stat = path.stat()
                stamp = f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}"
            except Exception:
                stamp = str(path)
            return hashlib.sha256(stamp.encode("utf-8")).hexdigest()[:12]

    def render_control_html(self, template_path: Path, css_path: Path, js_path: Path) -> str:
        html = self.read_asset_text(template_path)
        html = html.replace("{{CONTROL_CSS_VERSION}}", self.asset_version_token(css_path))
        html = html.replace("{{CONTROL_JS_VERSION}}", self.asset_version_token(js_path))
        return html


CONTROL_ASSETS_SERVICE = ControlAssetsService()