# scratch_db_update.py
from app import db, User, app  # Use the existing Flask app and db

def check_and_update_users():
    with app.app_context():  # Needed to access db outside Flask routes
        users = User.query.all()
        print(f"🔹 Found {len(users)} users in the database.\n")

        for user in users:
            print(f"User ID: {user.id}, Username: {user.username}, Downloads: {user.download_count}, Subscription: {user.subscription_type}")

            # Example check: reset download_count if user id == 1
            if user.id == 1:
                print(f"⚠️ Resetting download_count for {user.username}")
                user.download_count = 0

        db.session.commit()  # Save all changes at once
        print("\n✅ Done updating users.")

if __name__ == "__main__":
    check_and_update_users()
