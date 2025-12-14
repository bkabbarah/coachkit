from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime, timedelta

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

    def days_since_checkin(self):
        if not self.last_checkin:
            return 999
        delta = datetime.utcnow() - self.last_checkin
        return delta.days
    
    def is_at_risk(self, threshold_days=5):
        return self.days_since_checkin() >= threshold_days

class CheckIn(Base):
    __tablename__ = "checkins"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    note = Column(Text)
    weight = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="checkins")