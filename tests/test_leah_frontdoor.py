import unittest

from services.leah_frontdoor import LeahFrontdoorService


class TestLeahFrontdoorService(unittest.TestCase):
    def setUp(self):
        self.service = LeahFrontdoorService(
            asset_service=object(),
            template_path_provider=lambda: __import__("pathlib").Path("template.html"),
            css_path_provider=lambda: __import__("pathlib").Path("style.css"),
            js_path_provider=lambda: __import__("pathlib").Path("app.js"),
            upload_root_provider=lambda: __import__("pathlib").Path("uploads"),
        )

    def test_image_attachment_with_vision_intent_routes_to_spine(self):
        reply = self.service.maybe_answer_attachment_turn(
            "what do you see?",
            [
                {
                    "name": "desk.png",
                    "original_name": "desk.png",
                    "path": r"C:\nova\runtime\leah_uploads\desk.png",
                    "mime": "image/png",
                    "source": "upload",
                }
            ],
        )
        self.assertIsNone(reply)

    def test_text_attachment_stays_on_nova_spine(self):
        reply = self.service.maybe_answer_attachment_turn(
            "can you read it?",
            [
                {
                    "name": "note.txt",
                    "original_name": "note.txt",
                    "path": r"C:\nova\runtime\leah_uploads\note.txt",
                    "mime": "text/plain",
                    "source": "upload",
                }
            ],
        )
        self.assertIsNone(reply)


if __name__ == "__main__":
    unittest.main()