#!/usr/bin/env python3
"""
Create Admin User Script.

Creates an admin user directly in the database.
Useful for initial setup when no admin exists.

Usage:
    uv run python auto/create_admin.py
    uv run python auto/create_admin.py --email admin@example.com --password Secret123

Interactive Mode (no arguments):
    uv run python auto/create_admin.py
    # Script will prompt for each value

Environment Variables:
    ADMIN_EMAIL: Admin email (default: admin@example.com)
    ADMIN_PASSWORD: Admin password (default: auto-generated)
    ADMIN_USERNAME: Admin username (default: admin)
    ADMIN_FIRST_NAME: First name (default: Admin)
    ADMIN_LAST_NAME: Last name (default: User)
"""

from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
from asyncio import run as asyncio_run
from dataclasses import dataclass
from getpass import getpass
from os import environ
from pathlib import Path
from secrets import token_urlsafe
from sys import exit as sys_exit
from sys import path as sys_path
from traceback import print_exc
from typing import cast
from uuid import uuid4

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys_path.insert(0, str(project_root))

try:
    from sqlmodel import Column, select

    from app.db.database import transaction
    from app.managers.password_manager import hash_password
    from app.models import UserDB
except ImportError:
    # Re-add project root to path if import fails
    sys_path.append(str(project_root))
    from sqlalchemy import Column, select

    from app.db.database import transaction
    from app.managers.password_manager import hash_password
    from app.models import UserDB


@dataclass(frozen=True)
class AdminUserData:
    """
    Admin user creation data.

    Attributes
    ----------
    email : str
        Admin email address.
    password : str
        Admin password (will be hashed).
    username : str
        Admin username.
    first_name : str
        Admin first name.
    last_name : str
        Admin last name.
    country : str
        Admin country (default: Indonesia).
    """

    email: str
    password: str
    username: str
    first_name: str
    last_name: str
    country: str = "Indonesia"


@dataclass(frozen=True)
class AdminDisplayInfo:
    """
    Admin display information container.

    Attributes
    ----------
    email : str
        Admin email.
    username : str
        Admin username.
    first_name : str
        Admin first name.
    last_name : str
        Admin last name.
    country : str
        Admin country.
    password : str
        Admin password.
    auto_generated : bool
        Whether password was auto-generated.
    show_password : bool
        Whether to show password in output.
    """

    email: str
    username: str
    first_name: str
    last_name: str
    country: str
    password: str
    auto_generated: bool
    show_password: bool


def generate_secure_password(length: int = 16) -> str:
    """
    Generate a secure random password.

    Parameters
    ----------
    length : int
        Length of the random part (default: 16).

    Returns
    -------
    str
        Secure password with complexity requirements.
    """
    password = token_urlsafe(length)
    return f"Admin{password[:12]}!1"


def input_with_default(prompt: str, default: str) -> str:
    """
    Get user input with a default value.

    Parameters
    ----------
    prompt : str
        Input prompt to display.
    default : str
        Default value if user presses enter.

    Returns
    -------
    str
        User input or default value.
    """
    user_input = input(f"{prompt} [{default}]: ").strip()
    return user_input if user_input else default


def input_password() -> str:
    """
    Get password from user securely.

    Returns
    -------
    str
        Password entered by user.
    """
    print("\nPassword options:")
    print("  1. Enter your own password")
    print("  2. Auto-generate a secure password")
    choice = input("Select option [2]: ").strip() or "2"

    if choice == "1":
        while True:
            password = getpass("Enter password: ")
            if len(password) < 8:
                print("❌ Password must be at least 8 characters.")
                continue
            confirm = getpass("Confirm password: ")
            if password != confirm:
                print("❌ Passwords do not match.")
                continue
            return password
    else:
        password = generate_secure_password()
        print(f"\n✅ Auto-generated password: {password}")
        print("⚠️  Please save this password now! You won't see it again.")
        return password


def interactive_input() -> AdminUserData:
    """
    Get admin user data through interactive prompts.

    Returns
    -------
    AdminUserData
        Admin user data from user input.
    """
    print("=" * 60)
    print("Create Admin User - Interactive Mode")
    print("=" * 60)
    print("Press Enter to accept default values shown in [brackets]\n")

    email = input_with_default("Email", environ.get("ADMIN_EMAIL", "admin@example.com"))
    username = input_with_default("Username", environ.get("ADMIN_USERNAME", "admin"))
    first_name = input_with_default("First Name", environ.get("ADMIN_FIRST_NAME", "Admin"))
    last_name = input_with_default("Last Name", environ.get("ADMIN_LAST_NAME", "User"))
    country = input_with_default("Country", environ.get("ADMIN_COUNTRY", "Indonesia"))
    password = input_password()

    return AdminUserData(
        email=email,
        password=password,
        username=username,
        first_name=first_name,
        last_name=last_name,
        country=country,
    )


def display_admin_info(info: AdminDisplayInfo) -> None:
    """
    Display admin user creation information.

    Parameters
    ----------
    info : AdminDisplayInfo
        Admin display information container.
    """
    print("=" * 60)
    print("Creating Admin User")
    print("=" * 60)
    print(f"Email:      {info.email}")
    print(f"Username:   {info.username}")
    print(f"First Name: {info.first_name}")
    print(f"Last Name:  {info.last_name}")
    print(f"Country:    {info.country}")

    if info.auto_generated or info.show_password:
        print(f"Password:   {info.password}")
        if info.auto_generated:
            print("\n⚠️  NOTE: This password was auto-generated. Save it now!")
    else:
        print("Password:   (hidden)")

    print("-" * 60)


def display_success(admin: UserDB) -> None:
    """
    Display success message with admin details.

    Parameters
    ----------
    admin : UserDB
        Created admin user.
    """
    print("\n✅ Admin user created successfully!")
    print(f"   UUID:  {admin.uuid}")
    print(f"   Email: {admin.email}")
    print(f"   Role:  {admin.role}")
    print("\nYou can now login with:")
    print("  curl -X POST 'http://localhost:8000/auth/login' \\")
    print("    -H 'Content-Type: application/x-www-form-urlencoded' \\")
    print(f"    -d 'username={admin.email}&password=YOUR_PASSWORD'")
    print("\nThen use the access_token to create users:")
    print("  curl -X POST 'http://localhost:8000/users/create' \\")
    print("    -H 'Authorization: Bearer YOUR_TOKEN' \\")
    print("    -H 'Content-Type: application/json' \\")
    print("    -d '{...user data...}'")


async def create_admin_user(admin_data: AdminUserData) -> UserDB:
    """
    Create an admin user in the database.

    Parameters
    ----------
    admin_data : AdminUserData
        Admin user data container.

    Returns
    -------
    UserDB
        Created admin user.

    Raises
    ------
    ValueError
        If user with email or username already exists.
    """
    async with transaction() as session:
        email_clause = cast(Column[bool], UserDB.email == admin_data.email)
        existing_email = await session.execute(
            select(UserDB).where(email_clause),
        )
        if existing_email.scalar_one_or_none():
            msg = f"User with email '{admin_data.email}' already exists"
            raise ValueError(msg)

        username_clause = cast(Column[bool], UserDB.username == admin_data.username)
        existing_username = await session.execute(
            select(UserDB).where(username_clause),
        )
        if existing_username.scalar_one_or_none():
            msg = f"User with username '{admin_data.username}' already exists"
            raise ValueError(msg)

        password_hash = await hash_password(admin_data.password)

        admin_user = UserDB(
            uuid=uuid4(),
            username=admin_data.username,
            email=admin_data.email,
            password_hash=password_hash,
            first_name=admin_data.first_name,
            last_name=admin_data.last_name,
            is_verified=True,
            role="admin",
            country=admin_data.country,
            profile_picture=None,
            bio=None,
            website=None,
            date_of_birth=None,
            gender=None,
            phone_number=None,
        )

        session.add(admin_user)
        await session.commit()
        await session.refresh(admin_user)

        return admin_user


def get_admin_data_from_args(args: Namespace) -> AdminUserData | None:
    """
    Build AdminUserData from command line arguments.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command line arguments.

    Returns
    -------
    AdminUserData | None
        Admin data if all required args provided, None otherwise.
    """
    # If no email provided, return None to trigger interactive mode
    if args.email is None and not args.interactive:
        # Check if we have env vars set
        email = environ.get("ADMIN_EMAIL", "admin@example.com")
        password = args.password or environ.get("ADMIN_PASSWORD")
        username = args.username or environ.get("ADMIN_USERNAME", "admin")
        first_name = args.first_name or environ.get("ADMIN_FIRST_NAME", "Admin")
        last_name = args.last_name or environ.get("ADMIN_LAST_NAME", "User")
        country = args.country or environ.get("ADMIN_COUNTRY", "Indonesia")

        # If password not provided via args or env, go interactive
        if password is None:
            return None

        return AdminUserData(
            email=email,
            password=password,
            username=username,
            first_name=first_name,
            last_name=last_name,
            country=country,
        )

    # If email is explicitly provided, use it
    if args.email:
        email = args.email
        password = args.password
        username = args.username or "admin"
        first_name = args.first_name or "Admin"
        last_name = args.last_name or "User"
        country = args.country or "Indonesia"

        # Auto-generate password if not provided
        if password is None:
            password = generate_secure_password()

        return AdminUserData(
            email=email,
            password=password,
            username=username,
            first_name=first_name,
            last_name=last_name,
            country=country,
        )

    return None


def gather_input(args: Namespace) -> tuple[AdminUserData, bool] | None:
    """
    Gather all user input synchronously before async operations.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command line arguments.

    Returns
    -------
    tuple[AdminUserData, bool] | None
        Tuple of (admin_data, show_password) or None if cancelled.
    """
    # Try to get data from command line args first
    admin_data = get_admin_data_from_args(args)

    # If not enough args provided or --interactive flag, use interactive mode
    if admin_data is None or args.interactive:
        try:
            admin_data = interactive_input()
        except (KeyboardInterrupt, EOFError):
            print("\n\n❌ Cancelled by user.")
            return None

    show_password = args.show_password

    # Display info and confirm
    display_info = AdminDisplayInfo(
        email=admin_data.email,
        username=admin_data.username,
        first_name=admin_data.first_name,
        last_name=admin_data.last_name,
        country=admin_data.country,
        password=admin_data.password,
        auto_generated=False,  # Always show password in confirmation
        show_password=True,
    )
    display_admin_info(display_info)

    # Confirm before creating
    try:
        confirm = input("\nCreate admin user? [Y/n]: ").strip().lower()
        if confirm and confirm not in ("y", "yes"):
            print("❌ Cancelled.")
            return None
    except (KeyboardInterrupt, EOFError):
        print("\n\n❌ Cancelled by user.")
        return None

    return admin_data, show_password


def parse_args() -> Namespace:
    """
    Parse command line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed arguments with defaults applied.
    """
    parser = ArgumentParser(
        description="Create an admin user in the database.",
        formatter_class=RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (prompts for values)
  uv run python auto/create_admin.py or uv run python auto/create_admin.py --interactive

  # Command-line arguments
  uv run python auto/create_admin.py -e admin@mysite.com -p MySecurePass123

  # All custom fields
  uv run python auto/create_admin.py \\
    --email boss@company.com \\
    --password SuperSecret! \\
    --username boss \\
    --first-name "Big" \\
    --last-name "Boss"
        """,
    )

    parser.add_argument(
        "-e",
        "--email",
        default=None,
        help="Admin email (default: admin@example.com or ADMIN_EMAIL env var)",
    )
    parser.add_argument(
        "-p",
        "--password",
        default=None,
        help="Admin password (default: auto-generated or ADMIN_PASSWORD env var)",
    )
    parser.add_argument(
        "-u",
        "--username",
        default=None,
        help="Admin username (default: admin or ADMIN_USERNAME env var)",
    )
    parser.add_argument(
        "-f",
        "--first-name",
        default=None,
        help="Admin first name (default: Admin or ADMIN_FIRST_NAME env var)",
    )
    parser.add_argument(
        "-l",
        "--last-name",
        default=None,
        help="Admin last name (default: User or ADMIN_LAST_NAME env var)",
    )
    parser.add_argument(
        "-c",
        "--country",
        default=None,
        help="Admin country (default: Indonesia or ADMIN_COUNTRY env var)",
    )
    parser.add_argument(
        "--show-password",
        "-s",
        action="store_true",
        help="Show the password in output (use with caution)",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Force interactive mode even if arguments are provided",
    )

    return parser.parse_args()


async def main() -> int:
    """
    Run the admin creation process.

    Returns
    -------
    int
        Exit code (0 for success, 1 for error).
    """
    args = parse_args()

    # Gather all input synchronously first
    result = gather_input(args)
    if result is None:
        return 1

    admin_data, show_password = result

    try:
        admin = await create_admin_user(admin_data)

        # Display success with appropriate password visibility
        if not show_password:
            print("\n✅ Admin user created successfully!")
            print(f"   UUID:  {admin.uuid}")
            print(f"   Email: {admin.email}")
            print(f"   Role:  {admin.role}")
        else:
            display_success(admin)
        return 0

    except ValueError as e:
        print(f"\n❌ Error: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"\n❌ Unexpected error: {e}")
        print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio_run(main())
    sys_exit(exit_code)
