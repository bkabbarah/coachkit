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

    #goals
    goal_weight = Column(Float)
    notes = Column(Text)

    checkins = relationship("CheckIn", back_populates="client", order_by="desc(CheckIn.created_at)", cascade="all, delete-orphan")

    def days_since_checkin(self):
        if not self.last_checkin:
            return 999
        delta = datetime.utcnow() - self.last_checkin
        return delta.days
    
    def is_at_risk(self, threshold_days=5):
        return self.days_since_checkin() >= threshold_days
    
    def current_weight(self):
        # get most recent weight from checkins
        for checkin in self.checkins:
            if checkin.weight:
                return checkin.weight
        return None
    
    def goal_progress(self):
        """Calculate progress toward goal weight (can be negative or over 100)"""
        current = self.current_weight()
        if not current or not self.goal_weight:
            return None
        
        # Find starting weight (oldest check-in with weight)
        starting = None
        for checkin in reversed(self.checkins):
            if checkin.weight:
                starting = checkin.weight
                break
        
        if not starting:
            return None
        
        # If only one check-in, that's both start and current
        if starting == current:
            return 0
        
        # If starting equals goal, we're done
        if starting == self.goal_weight:
            return 100
        
        # Calculate how far goal is from starting point
        total_distance = abs(starting - self.goal_weight)
        
        # Calculate how far current is from starting point, in the right direction
        # Positive means moving toward goal, negative means moving away
        if self.goal_weight < starting:
            # Losing weight goal: progress is positive when current < starting
            current_distance = starting - current
        else:
            # Gaining weight goal: progress is positive when current > starting
            current_distance = current - starting
        
        progress = (current_distance / total_distance) * 100
        return progress

class CheckIn(Base):
    __tablename__ = "checkins"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    note = Column(Text)
    weight = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="checkins")