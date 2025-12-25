import anthropic
import os
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def generate_reengagement_message(client_name: str, days_inactive: int, notes: str = "", recent_checkins: list = None) -> str:
    checkin_context = ""
    if recent_checkins:
        checkin_context = "Recent check-in history:\n"
        for checkin in recent_checkins[:5]:  # Last 5 check-ins
            checkin_context += f"- {checkin.created_at.strftime('%b %d')}: {checkin.note or 'No notes'}"
            if checkin.weight:
                checkin_context += f" (Weight: {checkin.weight} lbs)"
            checkin_context += "\n"
    
    prompt = f"""You are helping a fitness coach write a friendly, personalized re-engagement message to a client who hasn't checked in recently.

Client name: {client_name}
Days since last check-in: {days_inactive}
Coach's notes about this client: {notes or 'None'}
{checkin_context}

Write a short, warm message (2-3 sentences) that:
1. Acknowledges the gap without being guilt-trippy
2. References something specific if possible (their goals, recent progress)
3. Encourages them to check in
4. Sounds human, not like a robot

Just output the message, nothing else."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    return message.content[0].text