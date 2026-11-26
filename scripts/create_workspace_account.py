"""Provision a Ledger workspace account without passing passwords on the command line."""
import argparse
from getpass import getpass

from fastapi import HTTPException
from pydantic import ValidationError

from apps.api.routes.workspace import Credentials, database, provision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("customer", "analyst", "manager"))
    parser.add_argument("username")
    args = parser.parse_args()
    password = getpass("Password (12–128 characters): ")
    if password != getpass("Confirm password: "):
        parser.exit(1, "Passwords differ.\n")
    try:
        credentials = Credentials(username=args.username, password=password)
        with database() as db:
            provision(db, credentials, args.role)
    except ValidationError:
        parser.exit(1, "Check username format and password length.\n")
    except HTTPException as failure:
        parser.exit(1, failure.detail + "\n")
    print(f"Created {args.role} account {args.username}.")


if __name__ == "__main__":
    main()
