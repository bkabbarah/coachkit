from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime, timedelta

class Base(DeclarativeBase):
    pass

class Coach(Base):
    __tablename__ = "coaches"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    clients = relationship("Client", back_populates="coach", cascade="all, delete-orphan")

class Client(Base):
    __tablename__ = "clients"
    
    id = Column(Integer, primary_key=True)
    coach_id = Column(Integer, ForeignKey("coaches.id"), nullable=False)
    name = Column(String, nullable=False)
    email = Column(String)
    last_checkin = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="on_track")

    # Goals
    goal_weight = Column(Float)
    notes = Column(Text)

    coach = relationship("Coach", back_populates="clients")
    checkins = relationship("CheckIn", back_populates="client", order_by="desc(CheckIn.created_at)", cascade="all, delete-orphan")

    def days_since_checkin(self):
        if not self.last_checkin:
            return 999
        delta = datetime.utcnow() - self.last_checkin
        return delta.days
    
    def is_at_risk(self, threshold_days=5):
        return self.days_since_checkin() >= threshold_days
    
    def current_weight(self):
        for checkin in self.checkins:
            if checkin.weight:
                return checkin.weight
        return None
    
    def goal_progress(self):
        current = self.current_weight()
        if not current or not self.goal_weight:
            return None
        
        starting = None
        for checkin in reversed(self.checkins):
            if checkin.weight:
                starting = checkin.weight
                break
        
        if not starting:
            return None
        
        if starting == current:
            return 0
        
        if starting == self.goal_weight:
            return 100
        
        total_distance = abs(starting - self.goal_weight)
        
        if self.goal_weight < starting:
            current_distance = starting - current
        else:
            current_distance = current - starting
        
        progress = (current_distance / total_distance) * 100
        return progress


class CheckIn(Base):
    __tablename__ = "checkins"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    note = Column(Text)
    weight = Column(Float)
    photo = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="checkins")