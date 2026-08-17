import os
import django
from django.utils import timezone
from datetime import timedelta
import uuid

def reproduce():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onboarding.settings")
    django.setup()
    
    from application.models import Application, QuizSession, SessionQuestion, Question
    from application.assessment import compute_score
    
    print("Testing with aware datetimes (USE_TZ=True)...")
    app = Application.objects.create(first_name='Test', last_name='TZ', email=f'tz{uuid.uuid4().hex[:6]}@example.com')
    sess = QuizSession.objects.create(application=app)
    q = Question.objects.first()
    
    # Mix naive and aware if possible, or just check if it crashes with normal aware ones
    sq = SessionQuestion.objects.create(
        session=sess, 
        question=q, 
        position=0,
        served_at=timezone.now(),
        answered_at=timezone.now() + timedelta(seconds=10)
    )
    
    try:
        score = compute_score(app)
        print(f"Score flags: {score['flags']}")
    except Exception as e:
        print(f"CRASH in compute_score: {type(e).__name__}: {e}")

    print("\nTesting for potential NoneType crash in compute_flags...")
    # This simulates a situation where served_at is None but answered_at is not (shouldn't happen but let's check)
    sq.served_at = None
    sq.answered_at = timezone.now()
    sq.save()
    
    try:
        score = compute_score(app)
        print(f"Score flags with partial None: {score['flags']}")
    except Exception as e:
        print(f"CRASH with partial None: {type(e).__name__}: {e}")

if __name__ == "__main__":
    reproduce()
