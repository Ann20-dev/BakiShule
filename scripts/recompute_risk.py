from app.db import SessionLocal
from app.services.clock import demo_today
from app.services.risk import recompute_all


if __name__ == "__main__":
    with SessionLocal() as db:
        snapshots = recompute_all(db, demo_today(db))
        print(f"Updated risk snapshots for {len(snapshots)} learners.")
