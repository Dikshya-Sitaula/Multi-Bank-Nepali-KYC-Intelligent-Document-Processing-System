"""Create a user account from the command line.

WHY: the system ships with no default accounts or passwords. The first administrator is
created with this script (or with the BOOTSTRAP_ADMIN_* env vars).

Run:
  .venv\\Scripts\\python.exe backend\\scripts\\create_user.py admin --role admin
  (the password is prompted for and never echoed; --password-env NAME reads it from an
  environment variable for non-interactive use)
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.database.session import session_scope  # noqa: E402
from app.main import run_migrations  # noqa: E402
from app.models import Role, User  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Create a user account.")
    ap.add_argument("username")
    ap.add_argument("--role", choices=[r.value for r in Role], default=Role.employee.value)
    ap.add_argument("--full-name", default=None)
    ap.add_argument("--password-env", default=None, help="read the password from this environment variable")
    args = ap.parse_args()

    if args.password_env:
        password = os.environ.get(args.password_env, "")
    else:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 1

    run_migrations()
    with session_scope() as db:
        if db.execute(select(User.id).where(func.lower(User.username) == args.username.lower())).first():
            print(f"User '{args.username}' already exists.", file=sys.stderr)
            return 1
        db.add(User(username=args.username, full_name=args.full_name, role=Role(args.role),
                    password_hash=hash_password(password)))
    print(f"Created {args.role} '{args.username}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
