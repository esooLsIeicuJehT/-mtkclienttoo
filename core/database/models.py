# core/database/models.py
"""
SQL database models for device history tracking.
Based on Eclipse Master Suite patterns.
"""
from datetime import datetime
from typing import Optional

try:
    from sqlmodel import SQLModel, Field
    SQLMODEL_AVAILABLE = True
except ImportError:
    SQLMODEL_AVAILABLE = False


if SQLMODEL_AVAILABLE:
    class DeviceRecord(SQLModel, table=True):
        """The central hardware inventory tracker."""
        __tablename__ = "devices"

        id: Optional[int] = Field(default=None, primary_key=True)
        device_id: str = Field(index=True, unique=True)
        vid: int = Field(default=0)
        pid: int = Field(default=0)
        last_interface: str = Field(default="unknown")
        status: str = Field(default="unknown")
        first_seen: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
        last_seen: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
        chipset_name: str = Field(default="Unknown")
        hw_code: int = Field(default=0)

    class DetectionHistory(SQLModel, table=True):
        """Tracks historical detection events."""
        __tablename__ = "detection_history"

        id: Optional[int] = Field(default=None, primary_key=True)
        timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
        device_id: str
        action: str
        details: str
else:
    # Fallback dataclasses
    from dataclasses import dataclass
    
    @dataclass
    class DeviceRecord:
        """Simple device record for when SQLModel is not available."""
        device_id: str
        vid: int = 0
        pid: int = 0
        last_interface: str = "unknown"
        status: str = "unknown"
        first_seen: str = datetime.utcnow().isoformat()
        last_seen: str = datetime.utcnow().isoformat()
        chipset_name: str = "Unknown"
        hw_code: int = 0

    @dataclass  
    class DetectionHistory:
        """Detection event for tracking."""
        timestamp: str = datetime.utcnow().isoformat()
        device_id: str = ""
        action: str = ""
        details: str = ""