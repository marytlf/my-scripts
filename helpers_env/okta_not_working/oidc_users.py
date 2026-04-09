import json
import os

USERS_FILE = "oidc_users.json"

# --- Default users loaded at startup ---
DEFAULT_USERS = [
    {
        "sub": "u-b5ie3sr373",
        "email": "rancheruser@mockoidc.local",
        "name": "Rancher Test User",
        "username": "rancheruser",
        "password": "password123",
        "groups": ["engineering", "devops", "rancher-admins"],
    }
]


def load_users() -> dict:
    """Load users from JSON file, or return defaults if file doesn't exist."""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            users_list = json.load(f)
        return {u["username"]: u for u in users_list}
    # First run: persist defaults
    save_users({u["username"]: u for u in DEFAULT_USERS})
    return {u["username"]: u for u in DEFAULT_USERS}


def save_users(users: dict):
    """Persist users dict to JSON file."""
    with open(USERS_FILE, "w") as f:
        json.dump(list(users.values()), f, indent=2)
    print(f"[+] Saved {len(users)} user(s) to {USERS_FILE}")


def list_users(users: dict):
    """Pretty-print all users."""
    if not users:
        print("No users found.")
        return
    print(f"\n{'─'*60}")
    print(f"  {'USERNAME':<20} {'EMAIL':<30} {'GROUPS'}")
    print(f"{'─'*60}")
    for u in users.values():
        groups = ", ".join(u.get("groups", []))
        print(f"  {u['username']:<20} {u['email']:<30} {groups}")
    print(f"{'─'*60}\n")


def add_user(users: dict):
    """Interactively add a single user."""
    print("\n--- Add New User ---")
    username = input("Username: ").strip()
    if username in users:
        print(f"[!] User '{username}' already exists.")
        return users

    sub       = input(f"Subject ID (e.g. u-abc123) [auto]: ").strip() or f"u-{username[:6]}001"
    email     = input(f"Email [{username}@mockoidc.local]: ").strip() or f"{username}@mockoidc.local"
    name      = input(f"Display name [{username}]: ").strip() or username
    password  = input("Password [password123]: ").strip() or "password123"
    groups_in = input("Groups (comma-separated) [engineering]: ").strip() or "engineering"
    groups    = [g.strip() for g in groups_in.split(",")]

    users[username] = {
        "sub": sub,
        "email": email,
        "name": name,
        "username": username,
        "password": password,
        "groups": groups,
    }
    print(f"[+] User '{username}' added.")
    return users


def add_bulk_users(users: dict):
    """Add multiple users from a JSON file or inline JSON."""
    print("\n--- Bulk Add Users ---")
    print("Provide path to a JSON file OR paste JSON directly.")
    source = input("File path or JSON: ").strip()

    try:
        # Try as file path first
        if os.path.exists(source):
            with open(source) as f:
                new_users = json.load(f)
        else:
            new_users = json.loads(source)

        if not isinstance(new_users, list):
            print("[!] JSON must be a list of user objects.")
            return users

        added = 0
        for u in new_users:
            uname = u.get("username")
            if not uname:
                print(f"[!] Skipping entry with no 'username': {u}")
                continue
            if uname in users:
                print(f"[!] Skipping duplicate: {uname}")
                continue
            # Apply defaults for missing fields
            u.setdefault("sub",      f"u-{uname[:6]}001")
            u.setdefault("email",    f"{uname}@mockoidc.local")
            u.setdefault("name",     uname)
            u.setdefault("password", "password123")
            u.setdefault("groups",   ["engineering"])
            users[uname] = u
            added += 1

        print(f"[+] Added {added} user(s).")
    except (json.JSONDecodeError, Exception) as e:
        print(f"[!] Error parsing input: {e}")

    return users


def delete_user(users: dict):
    """Remove a user by username."""
    print("\n--- Delete User ---")
    list_users(users)
    username = input("Username to delete: ").strip()
    if username not in users:
        print(f"[!] User '{username}' not found.")
        return users
    del users[username]
    print(f"[+] User '{username}' deleted.")
    return users


def generate_bulk_template():
    """Print a ready-to-use JSON template for bulk import."""
    template = [
        {
            "username": "alice",
            "sub": "u-alice001",
            "email": "alice@mockoidc.local",
            "name": "Alice Example",
            "password": "password123",
            "groups": ["engineering", "devops"]
        },
        {
            "username": "bob",
            "sub": "u-bob001",
            "email": "bob@mockoidc.local",
            "name": "Bob Example",
            "password": "password123",
            "groups": ["engineering"]
        }
    ]
    print("\n--- Bulk Import Template ---")
    print(json.dumps(template, indent=2))
    print("\nSave the above to a .json file and use option [3] to import it.\n")


def main():
    users = load_users()
    print(f"[*] Loaded {len(users)} user(s) from store.")

    while True:
        print("\n=== OIDC User Manager ===")
        print("[1] List users")
        print("[2] Add single user")
        print("[3] Bulk add users (from file or JSON)")
        print("[4] Delete user")
        print("[5] Show bulk import template")
        print("[6] Save & exit")
        print("[0] Exit without saving")

        choice = input("\nChoice: ").strip()

        if choice == "1":
            list_users(users)
        elif choice == "2":
            users = add_user(users)
        elif choice == "3":
            users = add_bulk_users(users)
        elif choice == "4":
            users = delete_user(users)
        elif choice == "5":
            generate_bulk_template()
        elif choice == "6":
            save_users(users)
            print("Bye!")
            break
        elif choice == "0":
            print("Exiting without saving.")
            break
        else:
            print("[!] Invalid choice.")


if __name__ == "__main__":
    main()
