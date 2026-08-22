"""
Refresh Token Model for secure token rotation.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class RefreshToken(Base):
    """
    Refresh token for JWT token rotation.
    
    Security features:
    - Token rotation: Old token is invalidated when new one is issued
    - Family tracking: Detect token reuse attacks
    - Expiry: Tokens expire after 7 days
    """
    __tablename__ = "refresh_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(256), unique=True, nullable=False, index=True)
    family_id = Column(String(36), nullable=False, index=True)  # UUID for token family
    is_revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    user_agent = Column(String(500), nullable=True)  # Browser/device info
    ip_address = Column(String(45), nullable=True)   # IPv6 max length
    
    # Relationship
    user = relationship("User", backref="refresh_tokens")
    
    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.now(timezone.utc) > self.expires_at
    
    @property
    def is_valid(self) -> bool:
        """Check if token is valid (not revoked and not expired)."""
        return not self.is_revoked and not self.is_expired
