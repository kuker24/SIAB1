"""
System Settings Model
Stores global system configuration including developer mode toggle
"""
from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
from app.core.apk_profiles import parse_token_profiles, parse_signature_profiles


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)

    # Developer/Testing Mode
    allow_browser_testing = Column(Boolean, default=False, nullable=False)

    # Mobile Apps Access (Independent from developer mode)
    allow_mobile_apps = Column(Boolean, default=True, nullable=False)

    # Maintenance Mode
    maintenance_mode = Column(Boolean, default=False, nullable=False)

    # Emergency Freeze Mode (global lock for non-developer actions)
    freeze_mode = Column(Boolean, default=False, nullable=False)

    # APK Version Control - Minimum required build token
    minimum_apk_token = Column(String(100), nullable=True)

    # APK App Signatures (Comma separated hashes)
    allowed_signatures = Column(String, nullable=True)

    # Emergency bypass for APK token validation (Ctrl+Shift+Alt+K)
    token_validation_bypass = Column(Boolean, default=False, nullable=False)

    # App Branding & Config
    app_name = Column(String(100), default="SIAB1", nullable=True)
    timezone = Column(String(50), default="Asia/Jakarta", nullable=True)

    # Audit fields
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # Added index for performance

    # Relationships
    updater = relationship("User", foreign_keys=[updated_by])

    def to_dict(self):
        """Convert to dictionary for API responses"""
        token_profiles = parse_token_profiles(self.minimum_apk_token)
        signature_profiles = parse_signature_profiles(self.allowed_signatures)
        return {
            "allow_browser_testing": self.allow_browser_testing,
            "allow_mobile_apps": self.allow_mobile_apps,
            "maintenance_mode": self.maintenance_mode,
            "freeze_mode": self.freeze_mode,
            "minimum_apk_token": self.minimum_apk_token,
            "allowed_signatures": self.allowed_signatures,
            "apk_token_profiles": {
                "stable": token_profiles.get("stable"),
                "stable_enabled": bool(token_profiles.get("stable_enabled", True)),
                "new_update": token_profiles.get("new_update"),
                "accepted_tokens": token_profiles.get("tokens", []),
            },
            "apk_signature_profiles": {
                "stable": signature_profiles.get("stable", []),
                "new_update": signature_profiles.get("new_update", []),
                "accepted_signatures": signature_profiles.get("all_signatures", []),
            },
            "token_validation_bypass": self.token_validation_bypass,
            "app_name": self.app_name or "SIAB1",
            "timezone": self.timezone or "Asia/Jakarta",
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "updated_by": self.updated_by
        }
