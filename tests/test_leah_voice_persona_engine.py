from __future__ import annotations

import json
import tempfile
from pathlib import Path

from services.leah_voice_persona_engine import (
    LEAH_VOICE_PERSONA_ENGINE_SERVICE,
    PERSONAS,
    VoicePersona,
    LeahVoicePersonaEngineService,
    _apply_persona_to_response,
    _detect_dominant_persona,
    _hour_of_day,
    _score_personas,
    _select_persona_by_hour,
    capability_registration,
)


def test_capability_registration():
    reg = capability_registration()
    assert "leah_voice_persona_engine" in reg
    assert isinstance(reg["leah_voice_persona_engine"], str)


def test_personas_defined():
    assert "formal" in PERSONAS
    assert "casual" in PERSONAS
    assert "friendly" in PERSONAS
    assert "professional" in PERSONAS
    assert "empathetic" in PERSONAS
    assert "enthusiastic" in PERSONAS
    assert len(PERSONAS) == 6


def test_persona_frozen():
    p = PERSONAS["formal"]
    assert p.persona_id == "formal"
    assert p.tts_voice == "Zira"
    assert p.tts_rate == 160


def test_hour_of_day():
    h = _hour_of_day(now=1726000000)
    assert 0 <= h <= 23


def test_select_persona_by_hour_morning():
    assert _select_persona_by_hour(8) == "friendly"


def test_select_persona_by_hour_afternoon():
    assert _select_persona_by_hour(14) == "casual"


def test_select_persona_by_hour_evening():
    assert _select_persona_by_hour(20) == "formal"


def test_select_persona_by_hour_night():
    assert _select_persona_by_hour(3) == "formal"


def test_score_personas_formal():
    scores = _score_personas("Could you please assist me with this matter?", 10)
    top_id, top_score = scores[0]
    assert top_id == "formal"
    assert top_score > 0


def test_score_personas_casual():
    scores = _score_personas("hey whats up dude", 14)
    top_id, top_score = scores[0]
    assert top_id == "casual"
    assert top_score > 0


def test_score_personas_friendly():
    scores = _score_personas("hello how are you thanks for the help", 9)
    top_id, top_score = scores[0]
    assert top_id == "friendly"
    assert top_score > 0


def test_score_personas_professional():
    scores = _score_personas("please review the quarterly report and metrics", 11)
    top_id, top_score = scores[0]
    assert top_id == "professional"
    assert top_score > 0


def test_score_personas_empathetic():
    scores = _score_personas("im feeling sad and frustrated struggling with this problem", 15)
    top_id, top_score = scores[0]
    assert top_id == "empathetic"
    assert top_score > 0


def test_score_personas_enthusiastic():
    scores = _score_personas("this is amazing fantastic i love this breakthrough success", 10)
    top_id, top_score = scores[0]
    assert top_id == "enthusiastic"
    assert top_score > 0


def test_detect_dominant_persona_formal():
    assert _detect_dominant_persona("please kindly assist me with this matter", 10) == "formal"


def test_detect_dominant_persona_casual():
    assert _detect_dominant_persona("hey whats up", 14) == "casual"


def test_detect_dominant_persona_empty():
    result = _detect_dominant_persona("", 10)
    assert result in PERSONAS


def test_apply_persona_to_response_formal():
    persona = PERSONAS["formal"]
    result = _apply_persona_to_response("This is great!", persona)
    assert "!" not in result


def test_apply_persona_to_response_casual():
    persona = PERSONAS["casual"]
    result = _apply_persona_to_response("This is cool!", persona)
    assert "cool" in result


def test_apply_persona_to_response_empty():
    persona = PERSONAS["formal"]
    assert _apply_persona_to_response("", persona) == ""
    assert _apply_persona_to_response("   ", persona) == "   "


def test_engine_default_persona():
    engine = LeahVoicePersonaEngineService()
    assert engine.get_current_persona_id() == "friendly"
    assert engine.get_current_persona().persona_id == "friendly"


def test_engine_select_persona_force():
    engine = LeahVoicePersonaEngineService()
    persona = engine.select_persona(force="formal")
    assert persona.persona_id == "formal"
    assert engine.get_current_persona_id() == "formal"


def test_engine_select_persona_dynamic():
    engine = LeahVoicePersonaEngineService()
    persona = engine.select_persona(text="hey whats up dude", hour=14)
    assert persona.persona_id == "casual"


def test_engine_select_persona_manual_override_sticky():
    engine = LeahVoicePersonaEngineService()
    engine.select_persona(force="formal")
    engine.select_persona(text="hey whats up dude", hour=14)
    assert engine.get_current_persona_id() == "formal"


def test_engine_process_response():
    engine = LeahVoicePersonaEngineService()
    engine.select_persona(force="formal")
    result = engine.process_response("This is great!")
    assert isinstance(result, str)
    assert len(result) > 0


def test_engine_get_tts_config():
    engine = LeahVoicePersonaEngineService()
    config = engine.get_tts_config()
    assert "voice" in config
    assert "rate" in config
    assert "persona_id" in config


def test_engine_reset():
    engine = LeahVoicePersonaEngineService()
    engine.select_persona(force="formal")
    engine.process_response("test")
    engine.reset()
    assert engine.get_current_persona_id() == "friendly"
    status = engine.persona_status()
    assert status["turn_count"] == 0


def test_engine_persona_status():
    engine = LeahVoicePersonaEngineService()
    status = engine.persona_status()
    assert status["ok"] is True
    assert "persona_id" in status
    assert "available_personas" in status
    assert len(status["available_personas"]) == 6


def test_engine_load_save_state():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "test_state.json"
        engine = LeahVoicePersonaEngineService(state_path=state_path)
        engine.select_persona(force="professional")
        engine.process_response("test response")
        engine.save_state()

        engine2 = LeahVoicePersonaEngineService(state_path=state_path)
        engine2.load_state()
        assert engine2.get_current_persona_id() == "professional"
        assert engine2.persona_status()["turn_count"] == 1


def test_engine_load_state_missing_file():
    engine = LeahVoicePersonaEngineService(state_path=Path("/nonexistent/path.json"))
    engine.load_state()
    assert engine.get_current_persona_id() == "friendly"


def test_engine_preference_learning():
    engine = LeahVoicePersonaEngineService()
    for _ in range(5):
        engine.select_persona(force="empathetic")
    engine._manual_override = False
    engine._current_persona_id = "friendly"
    engine.select_persona(text="hello", hour=10)
    assert engine.persona_status()["preference_scores"]["empathetic"] > 0


def test_engine_persona_history():
    engine = LeahVoicePersonaEngineService()
    engine.select_persona(force="formal")
    engine.select_persona(force="casual")
    status = engine.persona_status()
    assert len(status["recent_selections"]) == 2


def test_global_service_exists():
    assert LEAH_VOICE_PERSONA_ENGINE_SERVICE is not None
    assert isinstance(LEAH_VOICE_PERSONA_ENGINE_SERVICE, LeahVoicePersonaEngineService)
