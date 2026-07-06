# core/database/db_service.py
"""
Database service for device history tracking.
"""
import os
import platform
from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    from sqlmodel import create_engine, Session, select
    SQLMODEL_AVAILABLE = True
except ImportError:
    SQLMODEL_AVAILABLE = False

if platform.system() == "Windows":
    DB_PATH = os.path.join(os.environ.get("APPDATA", ""), "MTKClient2", "device_history.db")
else:
    DB_PATH = os.path.join(os.path.expanduser("~"), ".local", "share", "mtkclient2", "device_history.db")

# In-memory fallback
IN_MEMORY_HISTORY: List[Dict[str, Any]] = []


class DatabaseService:
    """Service for managing device history in SQLite database."""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DB_PATH
        self._engine = None
        
        if SQLMODEL_AVAILABLE:
            self._init_sqlite()
    
    def _init_sqlite(self):
        """Initialize SQLite database."""
        from .models import DeviceRecord, DetectionHistory, SQLModel
        
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        db_url = f"sqlite:///{self.db_path}"
        self._engine = create_engine(db_url, echo=False)
        SQLModel.metadata.create_all(self._engine)
        self.DeviceRecord = DeviceRecord
        self.DetectionHistory = DetectionHistory
    
    def record_device(self, device_id: str, vid: int, pid: int, 
                     interface: str = "unknown", status: str = "connected",
                     chipset_name: str = "Unknown", hw_code: int = 0):
        """Record a device detection event."""
        if not SQLMODEL_AVAILABLE:
            IN_MEMORY_HISTORY.append({
                "device_id": device_id,
                "vid": vid,
                "pid": pid,
                "interface": interface,
                "status": status,
                "timestamp": datetime.utcnow().isoformat(),
            })
            return
        
        try:
            with Session(self._engine) as session:
                # Check if device exists
                existing = session.exec(
                    select(self.DeviceRecord).where(
                        self.DeviceRecord.device_id == device_id
                    )
                ).first()
                
                if existing:
                    existing.last_seen = datetime.utcnow().isoformat()
                    existing.status = status
                    existing.last_interface = interface
                    session.add(existing)
                else:
                    record = self.DeviceRecord(
                        device_id=device_id,
                        vid=vid,
                        pid=pid,
                        last_interface=interface,
                        status=status,
                        chipset_name=chipset_name,
                        hw_code=hw_code,
                    )
                    session.add(record)
                
                # Add to detection history
                history = self.DetectionHistory(
                    device_id=device_id,
                    action="DETECTED",
                    details=f"VID={hex(vid)}, PID={hex(pid)}, interface={interface}"
                )
                session.add(history)
                session.commit()
        except Exception:
            pass
    
    def get_history(self) -> List[Dict[str, Any]]:
        """Get device history as list of dicts."""
        if not SQLMODEL_AVAILABLE:
            return IN_MEMORY_HISTORY.copy()
        
        try:
            with Session(self._engine) as session:
                records = session.exec(
                    select(self.DeviceRecord).order_by(self.DeviceRecord.last_seen.desc())
                ).all()
                return [
                    {
                        "device_id": r.device_id,
                        "vid": r.vid,
                        "pid": r.pid,
                        "interface": r.last_interface,
                        "status": r.status,
                        "first_seen": r.first_seen,
                        "last_seen": r.last_seen,
                        "chipset": r.chipset_name,
                        "hw_code": r.hw_code,
                    }
                    for r in records
                ]
        except Exception:
            return []
    
    def clear_history(self):
        """Clear device history."""
        global IN_MEMORY_HISTORY
        IN_MEMORY_HISTORY.clear()