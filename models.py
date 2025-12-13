from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import DeclarativeBase, relationship
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

    checkins = relationship("CheckIn", back_populates="client", order_by="desc(CheckIn.created_at)")

class CheckIn(Base):
    __tablename__ = "checkins"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    note = Column(Text)
    weight = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="checkins")