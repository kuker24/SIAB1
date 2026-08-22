# app/models/security_event.py
"""
Security Events Model - Track security violations and tampering attempts
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class SecurityEvent(Base):
    """Model for tracking security events and violations"""
    __tablename__ = 'security_events'

    id = Column(Integer, primary_key=True)
    event_type = Column(String(50), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    session_id = Column(Integer, ForeignKey('exam_sessions.id'), nullable=True)

    # Request details
    ip_address = Column(String(45))  # IPv6 compatible
    user_agent = Column(Text)
    endpoint = Column(String(200))
    method = Column(String(10))

    # Security data
    app_signature = Column(String(128))
    app_version = Column(String(20))
    expected_signature = Column(String(128))

    # Additional context
    extra_data = Column(Text)  # JSON string
    severity = Column(String(20), default='medium')  # low, medium, high, critical

    # Timestamps
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = relationship('User', backref='security_events')
    session = relationship('ExamSession', backref='security_events')

    def to_dict(self):
        """Convert to dictionary"""
        import json
        return {
            'id': self.id,
            'event_type': self.event_type,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'endpoint': self.endpoint,
            'method': self.method,
            'app_signature': self.app_signature,
            'app_version': self.app_version,
            'severity': self.severity,
            'extra_data': json.loads(self.extra_data) if self.extra_data else None,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

    # @staticmethod
    # def log_event(event_type, request, user_id=None, session_id=None,
    #                app_signature=None, severity='medium', extra_data=None):
    #     """
    #     Helper method to log security event
    #     NOTE: This method was designed for synchronous Flask app and is disabled in FastAPI/Async version.
    #     Use direct DB session add/commit in async endpoints instead.
    #     """
    #     pass
