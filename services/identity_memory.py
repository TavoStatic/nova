"""
IdentityMemoryService - Encapsulates identity memory validity.

This service validates the narrow identity facts Nova is allowed to store as
identity memory. Chat routing and tool use are decided elsewhere by intent.
"""

import re


class IdentityMemoryService:
    """Service for identity memory text validation."""
    
    # Allowed identity memory prefixes
    ALLOWED_IDENTITY_PREFIXES = (
        "learned_fact: assistant_name=",
        "learned_fact: developer_name=",
        "learned_fact: developer_nickname=",
        "learned_fact: identity_binding=developer",
    )
    
    def __init__(self, normalize_text_fn=None):
        self.normalize_text = normalize_text_fn or self._default_normalize_text
    
    @staticmethod
    def _default_normalize_text(text: str) -> str:
        """Default text normalization: collapse whitespace."""
        return re.sub(r"\s+", " ", str(text or "").strip())
    
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
