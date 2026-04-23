import shutil
import unittest
import uuid
from pathlib import Path

from services import nova_knowledge_packs


WORK_TMP_ROOT = Path(__file__).resolve().parents[1] / "runtime" / "pytest_temp"


def _workspace_case_dir(prefix: str) -> Path:
    WORK_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORK_TMP_ROOT / f"{prefix}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestNovaKnowledgePacks(unittest.TestCase):
    def test_kb_search_returns_reference_block_for_active_pack(self):
        root = _workspace_case_dir("nova_knowledge_packs")
        try:
            packs_dir = root / "packs"
            pack_dir = packs_dir / "district-data"
            pack_dir.mkdir(parents=True, exist_ok=True)
            (pack_dir / "attendance.txt").write_text(
                "student_data attendance reporting rules cover excused and unexcused absences.",
                encoding="utf-8",
            )

            result = nova_knowledge_packs.kb_search(
                "student_data attendance rules",
                packs_dir=packs_dir,
                kb_active_pack_fn=lambda: "district-data",
                tokenize_fn=nova_knowledge_packs.tokenize,
                max_files=3,
                max_chars=2000,
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertIn("REFERENCE (knowledge pack: district-data)", result)
        self.assertIn("attendance.txt", result)
        self.assertIn("attendance reporting rules", result.lower())

    def test_build_local_topic_digest_answer_cites_matching_source(self):
        base_dir = _workspace_case_dir("nova_knowledge_packs")
        try:
            packs_dir = base_dir / "knowledge" / "packs"
            pack_dir = packs_dir / "district-data"
            pack_dir.mkdir(parents=True, exist_ok=True)
            topic_path = pack_dir / "tsds_overview.txt"
            topic_path.write_text(
                "TSDS is the Texas student_data System used for student_data collections.",
                encoding="utf-8",
            )

            result = nova_knowledge_packs.build_local_topic_digest_answer(
                "what is TSDS?",
                packs_dir=packs_dir,
                base_dir=base_dir,
                active_knowledge_root_fn=lambda: pack_dir,
                topic_tokens_fn=nova_knowledge_packs.topic_tokens,
                read_text_safely_fn=nova_knowledge_packs.read_text_safely,
                extract_matching_lines_fn=lambda text, tokens: nova_knowledge_packs.extract_matching_lines(text, tokens, max_lines=3),
            )
        finally:
            shutil.rmtree(base_dir, ignore_errors=True)

        self.assertIn("active knowledge pack (district-data)", result.lower())
        self.assertIn("tsds", result.lower())
        self.assertIn("knowledge/packs/district-data/tsds_overview.txt", result.lower())


if __name__ == "__main__":
    unittest.main()
