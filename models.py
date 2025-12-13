from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime

class Base(DeclarativeBase):
    pass

class Client(Base):
    __tablename__ = "clients"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String)
    last_checkin = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="on_track")