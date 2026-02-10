"""Email template builder for HTML email generation with mobile-first responsive design."""

from typing import cast

from app.configs import settings


class EmailTemplateBuilder:
    """
    Builder for creating professional HTML email templates.

    This class provides methods for constructing responsive, mobile-first HTML emails
    with consistent branding and styling. It supports various email components including
    headers, footers, buttons, security alerts, and info boxes.
    """

    # ==========================================================================
    # Email Template Styles - Reusable CSS Constants
    # ==========================================================================
    EMAIL_STYLES: dict[str, str | dict[str, str]] = {
        # Brand Colors
        "color_primary": "#1a2a6c",
        "color_accent": "#ce6f21",
        "color_warning_bg": "#fff3cd",
        "color_warning_border": "#ffeaa7",
        "color_warning_text": "#856404",
        "color_text_primary": "#333333",
        "color_text_secondary": "#666666",
        "color_text_muted": "#888888",
        "color_text_footer": "#999999",
        "color_bg_page": "#f4f7f9",
        "color_bg_container": "#ffffff",
        "color_bg_footer": "#f9f9f9",
        "color_border": "#eeeeee",
        "color_border_container": "rgba(10, 10, 10, 0.1)",
        # Typography
        "font_stack": "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif",
        "font_size_base_mobile": "14px",
        "font_size_base_desktop": "16px",
        "font_size_h1_mobile": "18px",
        "font_size_h1_desktop": "24px",
        "font_size_small": "14px",
        "font_size_footer": "12px",
        "line_height_base": "1.6",
        # Spacing (Mobile First)
        "padding_container_mobile": "16px",
        "padding_container_desktop": "40px",
        "padding_header_mobile": "20px",
        "padding_header_desktop": "30px",
        "padding_footer": "20px",
        "margin_container_mobile": "20px auto",
        "margin_container_desktop": "40px auto",
        "margin_button_top": "24px",
        "margin_paragraph_top": "16px",
        # Layout
        "max_width_container": "600px",
        "border_radius_large": "12px",
        "border_radius_medium": "8px",
        "border_radius_small": "6px",
        "box_shadow": "0 4px 12px rgba(0, 0, 0, 0.8)",
        "gradient_header": "linear-gradient(135deg, #1a2a6c, #b21f1f, #fdbb2d)",
        "logo_max_width": "150px",
        "button_min_height": "44px",  # Touch target size
        # Component-specific styles
        "button": {
            "padding": "14px 28px",
            "border_radius": "6px",
            "font_weight": "bold",
            "text_decoration": "none",
            "display": "inline-block",
            "min_height": "44px",
        },
        "security_box": {
            "padding": "16px",
            "border_radius": "8px",
            "background_color": "#fff3cd",
            "border": "1px solid #ffeaa7",
        },
        "info_box": {
            "padding": "16px",
            "border_radius": "8px",
            "background_color": "#f9f9f9",
            "border_left": "4px solid #ce6f21",
        },
    }

    # Logo URL constant
    LOGO_URL: str = (
        "https://res.cloudinary.com/dusikjnta/image/upload/"
        "f_auto/q_auto/v1/My%20Brand/bali_blissed_simplified_dhkbvy?_a=BAMAAAhK0"
    )

    def _get_logo_url(self) -> str:
        """
        Get the logo URL for email templates.

        Returns:
            str: The Cloudinary logo URL.
        """
        return self.LOGO_URL

    def _get_base_template(self) -> str:
        """
        Get the base email template with CSS styles.

        Returns:
            str: The base email template HTML with placeholders.
        """
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>{title}</title>
    <style>
        /* Reset styles */
        body, table, td, p, a, li, blockquote {{
            -webkit-text-size-adjust: 100%;
            -ms-text-size-adjust: 100%;
        }}
        table, td {{
            mso-table-lspace: 0pt;
            mso-table-rspace: 0pt;
        }}
        img {{
            -ms-interpolation-mode: bicubic;
            border: 0;
            height: auto;
            line-height: 100%;
            outline: none;
            text-decoration: none;
        }}
        /* Mobile-first base styles */
        body {{
            font-family: {font_stack};
            background-color: {color_bg_page};
            margin: 0;
            padding: 0;
            color: {color_text_primary};
        }}
        .container {{
            width: 100%;
            max-width: {max_width};
            margin: {margin_mobile};
            background-color: {color_bg_container};
            border-radius: {border_radius};
            overflow: hidden;
            box-shadow: {box_shadow};
            border: 1px solid {color_border_container};
        }}
        .header {{
            background: {gradient_header};
            padding: {padding_header_mobile};
            text-align: center;
        }}
        .header img {{
            max-width: {logo_width};
            height: auto;
        }}
        .content {{
            padding: {padding_mobile};
            text-align: center;
        }}
        .content h1 {{
            color: {color_primary};
            font-size: {font_h1_mobile};
            margin: 0 0 16px 0;
            line-height: 1.3;
        }}
        .content p {{
            line-height: {line_height};
            color: {color_text_secondary};
            font-size: {font_base_mobile};
            margin: 0 0 {para_margin} 0;
        }}
        .button-container {{
            margin-top: {button_margin};
        }}
        .button {{
            color: #ffffff !important;
            text-decoration: none;
            font-weight: bold;
            font-size: {font_base_mobile};
            padding: {button_padding};
            border-radius: {button_radius};
            background-color: {color_accent};
            display: inline-block;
            min-height: {button_min_height};
            line-height: {button_min_height};
            box-sizing: border-box;
            transition: background-color 0.3s;
        }}
        .button:hover {{
            background-color: #b85f1c;
        }}
        .footer {{
            background-color: {color_bg_footer};
            padding: {padding_footer};
            text-align: center;
            font-size: {font_footer};
            color: {color_text_footer};
            border-top: 1px solid {color_border};
        }}
        .footer p {{
            margin: 5px 0;
            color: {color_text_footer};
        }}
        .security-box {{
            margin-top: 20px;
            padding: {security_padding};
            background-color: {color_warning_bg};
            border-radius: {security_radius};
            border: {security_border};
            text-align: left;
        }}
        .security-box p {{
            margin: 0;
            font-size: {font_small};
            color: {color_warning_text};
        }}
        .info-box {{
            margin: 24px 0;
            padding: {info_padding};
            background-color: {color_bg_footer};
            border-radius: {info_radius};
            border-left: {info_border_left};
            text-align: left;
        }}
        .info-box p {{
            margin: 0;
            font-size: {font_small};
            color: {color_text_secondary};
        }}
        .expiry-note {{
            margin-top: 24px;
            font-size: {font_small};
            color: {color_text_muted};
        }}
        /* Desktop enhancements */
        @media screen and (min-width: 600px) {{
            .container {{
                margin: {margin_desktop};
            }}
            .header {{
                padding: {padding_header_desktop};
            }}
            .content {{
                padding: {padding_desktop};
            }}
            .content h1 {{
                font-size: {font_h1_desktop};
                margin-bottom: 20px;
            }}
            .content p {{
                font-size: {font_base_desktop};
                margin-bottom: 16px;
            }}
            .button {{
                font-size: {font_base_desktop};
            }}
        }}
        /* Dark mode support */
        @media (prefers-color-scheme: dark) {{
            body {{
                background-color: #1a1a1a;
            }}
            .container {{
                background-color: #2d2d2d;
            }}
            .content h1 {{
                color: #4a90e2;
            }}
            .content p {{
                color: #cccccc;
            }}
            .footer {{
                background-color: #252525;
                border-top-color: #3d3d3d;
            }}
        }}
    </style>
</head>
<body>
    {body_content}
</body>
</html>
"""

    def build_template(
        self,
        title: str,
        header_html: str,
        content_html: str,
        footer_html: str,
    ) -> str:
        """
        Build the complete email template with provided components.

        Args:
            title: The email title for the HTML head.
            header_html: The header section HTML (logo + branding).
            content_html: The main content section HTML.
            footer_html: The footer section HTML.

        Returns:
            str: The complete formatted HTML email.
        """
        body_content = f"""
    <div class="container">
        {header_html}
        {content_html}
        {footer_html}
    </div>
        """.strip()

        styles = self.EMAIL_STYLES
        button_styles = cast("dict[str, str]", styles["button"])
        security_styles = cast("dict[str, str]", styles["security_box"])
        info_styles = cast("dict[str, str]", styles["info_box"])

        return self._get_base_template().format(
            title=title,
            font_stack=styles["font_stack"],
            color_bg_page=styles["color_bg_page"],
            color_text_primary=styles["color_text_primary"],
            max_width=styles["max_width_container"],
            margin_mobile=styles["margin_container_mobile"],
            color_bg_container=styles["color_bg_container"],
            border_radius=styles["border_radius_large"],
            box_shadow=styles["box_shadow"],
            color_border_container=styles["color_border_container"],
            gradient_header=styles["gradient_header"],
            padding_header_mobile=styles["padding_header_mobile"],
            logo_width=styles["logo_max_width"],
            padding_mobile=styles["padding_container_mobile"],
            color_primary=styles["color_primary"],
            font_h1_mobile=styles["font_size_h1_mobile"],
            line_height=styles["line_height_base"],
            color_text_secondary=styles["color_text_secondary"],
            font_base_mobile=styles["font_size_base_mobile"],
            para_margin=styles["margin_paragraph_top"],
            button_margin=styles["margin_button_top"],
            button_padding=button_styles["padding"],
            button_radius=button_styles["border_radius"],
            button_min_height=button_styles["min_height"],
            color_accent=styles["color_accent"],
            color_bg_footer=styles["color_bg_footer"],
            padding_footer=styles["padding_footer"],
            font_footer=styles["font_size_footer"],
            color_text_footer=styles["color_text_footer"],
            color_border=styles["color_border"],
            color_warning_bg=styles["color_warning_bg"],
            security_padding=security_styles["padding"],
            security_radius=security_styles["border_radius"],
            security_border=security_styles["border"],
            font_small=styles["font_size_small"],
            color_warning_text=styles["color_warning_text"],
            info_padding=info_styles["padding"],
            info_radius=info_styles["border_radius"],
            info_border_left=info_styles["border_left"],
            margin_desktop=styles["margin_container_desktop"],
            padding_header_desktop=styles["padding_header_desktop"],
            padding_desktop=styles["padding_container_desktop"],
            font_h1_desktop=styles["font_size_h1_desktop"],
            font_base_desktop=styles["font_size_base_desktop"],
            color_text_muted=styles["color_text_muted"],
            body_content=body_content,
        )

    def build_header(self) -> str:
        """
        Build the email header HTML with logo.

        Returns:
            str: The header HTML section.
        """
        logo_url = self._get_logo_url()
        return f"""<div class="header">
            <img src="{logo_url}" alt="BaliBlissed Logo">
        </div>"""

    def build_footer(self, year: int) -> str:
        """
        Build the email footer HTML.

        Args:
            year: The current year for copyright.

        Returns:
            str: The footer HTML section.
        """
        return f"""<div class="footer">
            <p>&copy; {year} BaliBlissed. All rights reserved.</p>
            <p>Your portal to Bali's finest travel experiences.</p>
        </div>"""

    def build_button(self, url: str, text: str) -> str:
        """
        Build a styled CTA button HTML.

        Args:
            url: The button link URL.
            text: The button text.

        Returns:
            str: The button HTML.
        """
        return f"""<div class="button-container">
            <a href="{url}" class="button">{text}</a>
        </div>"""

    def build_security_box(self, message: str) -> str:
        """
        Build a security alert box HTML.

        Args:
            message: The HTML content of the security message.

        Returns:
            str: The security box HTML.
        """
        return f"""<div class="security-box">
            <p>{message}</p>
        </div>"""

    def build_info_box(self, content: str) -> str:
        """
        Build an info box HTML with accent border.

        Args:
            content: The HTML content for the info box.

        Returns:
            str: The info box HTML.
        """
        return f"""<div class="info-box">
            <p>{content}</p>
        </div>"""

    def build_content_wrapper(
        self,
        heading: str,
        paragraphs: list[str],
        button_html: str | None = None,
        expiry_note: str | None = None,
        extra_html: str | None = None,
    ) -> str:
        """
        Build the main content section with consistent structure.

        Args:
            heading: The main heading (h1) text.
            paragraphs: List of paragraph texts.
            button_html: Optional button HTML to include.
            expiry_note: Optional expiry note text.
            extra_html: Optional additional HTML (security boxes, etc.).

        Returns:
            str: The complete content section HTML.
        """
        paragraphs_html = "\n            ".join(f"<p>{p}</p>" for p in paragraphs)

        parts = [
            '<div class="content">',
            f"            <h1>{heading}</h1>",
            f"            {paragraphs_html}",
        ]

        if button_html:
            parts.append(f"            {button_html}")

        if expiry_note:
            parts.append(f'            <p class="expiry-note">{expiry_note}</p>')

        if extra_html:
            parts.append(f"            {extra_html}")

        parts.append("        </div>")

        return "\n        ".join(parts)

    def build_verification_email(
        self,
        greet_name: str,
        verification_link: str,
        expiry_hours: int,
        year: int,
    ) -> str:
        """
        Build the complete verification email HTML.

        Args:
            greet_name: The user's greeting name.
            verification_link: The email verification link.
            expiry_hours: Hours until the link expires.
            year: The current year for copyright.

        Returns:
            str: The complete HTML email.
        """
        header_html = self.build_header()
        footer_html = self.build_footer(year)
        button_html = self.build_button(verification_link, "Verify Email Address")

        content_html = self.build_content_wrapper(
            heading=f"Welcome to BaliBlissed, {greet_name}!",
            paragraphs=[
                "Thank you for embarking on your journey with us. To ensure the security "
                "of your account and access all our travel features, please verify your "
                "email address by clicking the button below.",
            ],
            button_html=button_html,
            expiry_note=f"This link will expire in {expiry_hours} hours.<br>"
            "If you didn't create an account, you can safely ignore this email.",
        )

        return self.build_template(
            title="Verify Your BaliBlissed Account",
            header_html=header_html,
            content_html=content_html,
            footer_html=footer_html,
        )

    def build_password_reset_email(
        self,
        greet_name: str,
        reset_link: str,
        expiry_hours: int,
        year: int,
    ) -> str:
        """
        Build the complete password reset email HTML.

        Args:
            greet_name: The user's greeting name.
            reset_link: The password reset link.
            expiry_hours: Hours until the link expires.
            year: The current year for copyright.

        Returns:
            str: The complete HTML email.
        """
        header_html = self.build_header()
        footer_html = self.build_footer(year)
        button_html = self.build_button(reset_link, "Reset Password")

        security_message = (
            "<strong>Security Tip:</strong><br>"
            "Never share this link with anyone. BaliBlissed will never ask for your password via email."
        )
        security_box_html = self.build_security_box(security_message)

        content_html = self.build_content_wrapper(
            heading="Reset Your Password",
            paragraphs=[
                f"Hi {greet_name},",
                "We received a request to reset your BaliBlissed account password. "
                "Click the button below to create a new password:",
            ],
            button_html=button_html,
            expiry_note=f"This link will expire in {expiry_hours} hour(s).<br>"
            "If you didn't request this reset, you can safely ignore this email.",
            extra_html=security_box_html,
        )

        return self.build_template(
            title="Reset Your BaliBlissed Password",
            header_html=header_html,
            content_html=content_html,
            footer_html=footer_html,
        )

    def build_password_change_email(
        self,
        greet_name: str,
        change_time: str,
        year: int,
    ) -> str:
        """
        Build the complete password change confirmation email HTML.

        Args:
            greet_name: The user's greeting name.
            change_time: The formatted change timestamp.
            year: The current year for copyright.

        Returns:
            str: The complete HTML email.
        """
        header_html = self.build_header()
        footer_html = self.build_footer(year)

        info_content = f"<strong>Change Time:</strong> {change_time}"
        info_box_html = self.build_info_box(info_content)

        security_message = (
            "<strong>Didn't make this change?</strong><br>"
            "If you didn't change your password, please contact us immediately at "
            f'<a href="mailto:{settings.COMPANY_TARGET_EMAIL}" style="color: #1a2a6c;">'
            f"{settings.COMPANY_TARGET_EMAIL}</a> to secure your account."
        )
        security_box_html = self.build_security_box(security_message)

        content_html = self.build_content_wrapper(
            heading="Password Changed Successfully",
            paragraphs=[
                f"Hi {greet_name},",
                "Your BaliBlissed account password was changed successfully.",
                "You will need to sign in again on all other devices with your new password.",
            ],
            extra_html=f"{info_box_html}\n            {security_box_html}",
        )

        return self.build_template(
            title="Your BaliBlissed Password Was Changed",
            header_html=header_html,
            content_html=content_html,
            footer_html=footer_html,
        )
