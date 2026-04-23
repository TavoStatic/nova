"""
IdentityMemoryService - Encapsulates identity-only session validation and memory gating logic.

This service manages:
- Identity-only session detection and enforcement
- Memory text validation against identity constraints
- Domain blocking for clean-slate sessions (location, weather, web, knowledge, memory)
- Deterministic reply generation for blocked operations
"""

import re
from typing import Optional


class IdentityMemoryService:
    """Service for managing identity-only session constraints and memory gating."""

    # Core identity-only markers
    IDENTITY_ONLY_MARKERS = frozenset(["clean_slate", "clean slate"])
    
    # Allowed identity memory prefixes
    ALLOWED_IDENTITY_PREFIXES = (
        "learned_fact: assistant_name=",
        "learned_fact: developer_name=",
        "learned_fact: developer_nickname=",
        "learned_fact: identity_binding=developer",
    )
    
    # Domain-specific blocked messages
    DOMAIN_BLOCKS = {
        "location": "This clean session is identity-only, so I won't store or use location here.",
        "weather": "This clean session is identity-only, so I won't run weather lookups here.",
        "web": "This clean session is identity-only, so I won't run web research here.",
        "knowledge": "This clean session is identity-only, so I won't use local knowledge grounding here.",
        "memory": "This clean session is identity-only, so I won't store general memory here.",
    }
    
    # Location utterance patterns (for identity-only mode detection)
    LOCATION_PATTERNS = (
        r"^\s*the\s+(\d{5})\s+is\s+the\s+zip\s+code\s+for\s+your\s+current\s+physical\s+location\s*[.!?]*$",
        r"^\s*my\s+zip\s+is\s+(.+?)\s*[.!?]*$",
        r"^\s*set\s+location\s+to\s+(.+?)\s*[.!?]*$",
        r"^\s*(?:my|your|the)(?:\s+(?:current|physical))?\s+location\s+is\s+(.+?)\s*[.!?]*$",
        r"^\s*i\s*(?:am|m)\s+in\s+(.+?)\s*[.!?]*$",
        r"^\s*i\s+am\s+located\s+in\s+(.+?)\s*[.!?]*$",
        r"^\s*you\s+are\s+located\s+in\s+(.+?)\s*[.!?]*$",
        r"^\s*(?:living|based)\s+in\s+(.+?)\s*[.!?]*$",
    )
    
    # Intent-to-block mapping
    INTENT_BLOCK_MAP = {
        "set_location": "location",
        "weather_lookup": "weather",
        "store_fact": "memory",
        "web_research_family": "web",
    }
    
    def __init__(self, normalize_text_fn=None, location_query_fn=None, location_name_fn=None, 
                 saved_location_weather_fn=None, peims_query_fn=None, declarative_info_fn=None):
        """
        Initialize the service with optional dependencies on text normalization and query classifiers.
        
        These functions allow the service to delegate complex pattern matching to nova_core
        while isolating the core gating logic here.
        """
        self.normalize_text = normalize_text_fn or self._default_normalize_text
        self.is_location_recall_query = location_query_fn or (lambda t: False)
        self.is_location_name_query = location_name_fn or (lambda t: False)
        self.is_saved_location_weather_query = saved_location_weather_fn or (lambda t: False)
        self.is_peims_broad_query = peims_query_fn or (lambda t: False)
        self.is_declarative_info = declarative_info_fn or (lambda t: False)
    
    @staticmethod
    def _default_normalize_text(text: str) -> str:
        """Default text normalization: collapse whitespace."""
        return re.sub(r"\s+", " ", str(text or "").strip())
    
    def is_identity_only_session(self, session_id: str) -> bool:
        """
        Check if a session is marked as identity-only (clean-slate mode).
        
        Args:
            session_id: Session identifier to check
            
        Returns:
            True if session is identity-only, False otherwise
        """
        if not session_id:
            return False
        normalized = self.normalize_text(session_id).lower()
        return any(marker in normalized for marker in self.IDENTITY_ONLY_MARKERS)
    
    def is_identity_memory_text_allowed(self, kind: str, text: str) -> bool:
        """
        Check if text is allowed to be stored in identity memory.
        
        Non-identity memory is always allowed. Identity memory is restricted to
        Nova's own identity and developer information.
        
        Args:
            kind: Memory kind (e.g., "identity", "fact")
            text: Memory text content
            
        Returns:
            True if text is allowed, False otherwise
        """
        if str(kind or "").strip().lower() != "identity":
            return True
        
        low = self.normalize_text(text).lower()
        if not low:
            return False
        
        if "nova_name_origin:" in low:
            return True
        
        return any(low.startswith(prefix) for prefix in self.ALLOWED_IDENTITY_PREFIXES)
    
    def looks_like_identity_only_location_text(self, user_text: str) -> bool:
        """
        Check if user text looks like a location-setting utterance.
        
        Uses explicit patterns to detect location declarations in identity-only mode.
        
        Args:
            user_text: User utterance to check
            
        Returns:
            True if text matches location patterns, False otherwise
        """
        raw = str(user_text or "").strip()
        if not raw:
            return False
        
        return any(re.match(pattern, raw, flags=re.I) for pattern in self.LOCATION_PATTERNS)
    
    def get_identity_only_block_kind(self, user_text: str, intent_result: Optional[dict] = None) -> str:
        """
        Determine if an identity-only session blocks a user request and return the block domain.
        
        Returns:
            One of: "location", "weather", "web", "knowledge", "memory", or "" (no block)
        """
        text = str(user_text or "").strip()
        low = self.normalize_text(text).strip().lower()
        intent = str((intent_result or {}).get("intent") or "").strip().lower()
        
        if not low and not intent:
            return ""
        
        # Check intent-based block first
        if intent in self.INTENT_BLOCK_MAP:
            return self.INTENT_BLOCK_MAP[intent]
        
        # Check text-based patterns
        if (self.looks_like_identity_only_location_text(text) or 
            self.is_location_recall_query(text) or 
            self.is_location_name_query(text)):
            return "location"
        
        if "weather" in low or self.is_saved_location_weather_query(text):
            return "weather"
        
        if self.is_peims_broad_query(text) or "peims" in low or "tsds" in low:
            return "knowledge"
        
        if self.is_declarative_info(text):
            return "memory"
        
        return ""
    
    def get_identity_only_block_reply(self, block_kind: str) -> str:
        """
        Get the reply message for a blocked operation in identity-only mode.
        
        Args:
            block_kind: One of the domain keys in DOMAIN_BLOCKS
            
        Returns:
            Domain-specific or generic block message
        """
        domain = str(block_kind or "").strip().lower()
        return self.DOMAIN_BLOCKS.get(domain, 
                                       "This clean session is identity-only, so I won't run non-identity routing here.")
