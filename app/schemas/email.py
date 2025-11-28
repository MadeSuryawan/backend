from pydantic import BaseModel, EmailStr, Field, field_validator

# Define a list of common disposable/temporary email domains
DISPOSABLE_DOMAINS: list[str] = [
    "mailinator.com",
    "temp-mail.org",
    "10minutemail.com",
    "yopmail.com",
    "guerrillamail.com",
    "mailpoof.com",
    "trashmail.com",
]


class EmailRequest(BaseModel):
    """Schema for incoming email requests, including validation checks."""

    subject: str = Field(
        ...,
        min_length=1,
        description="Subject of the email",
        examples=["Support Request"],
    )
    message: str = Field(
        ...,
        min_length=1,
        description="Message of the email",
        examples=["If you read this, the Python integration works! Try hitting Reply."],
    )
    email: EmailStr = Field(
        ...,
        min_length=1,
        description="Email of the user",
        examples=["jhondoe@gmail.com"],
    )

    # Validator runs after Pydantic's EmailStr validation passes
    @field_validator("email", mode="before")
    @classmethod  # Class method decorator for class-level validation
    def validate_disposable_domain(cls, value: str) -> str:
        """Check if the email domain is a known temporary mail service."""

        # Ensure the value is a string before proceeding
        if not isinstance(value, str):
            message = "Email must be a string."
            raise TypeError(message)

        # Split domain from email address
        try:
            domain = value.lower().split("@")[-1]
        except IndexError as e:
            # Should be caught by EmailStr, but safe check
            message = "Invalid email format."
            raise ValueError(message) from e

        if domain in DISPOSABLE_DOMAINS:
            message = f"Email domain '{domain}' is a known temporary mail service."
            raise ValueError(message)

        return value
