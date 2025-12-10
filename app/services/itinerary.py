# app/services/itinerary.py

from logging import getLogger
from typing import cast

# from anyio import Path
from fastapi import Request

from app.clients.ai_client import AiClient
from app.configs.settings import WHATSAPP_NUMBER, file_logger
from app.errors import host
from app.schemas.ai.itinerary import (
    ItineraryMD,
    ItineraryRequestMD,
    ItineraryRequestTXT,
    ItineraryTXT,
)

# from app.utils import md_to_text
from app.utils import clean_markdown

# from app.utils import save_to_file

logger = file_logger(getLogger(__name__))


def topics(duration: int) -> str:
    """
    Itinerary topics analysis.

    Args:
        duration: The duration of the itinerary.

    Returns:
        A formatted itinerary topics string.
    """

    # 🚗 **TRANSPORTATION & LOGISTICS**
    # - **1** Getting to/from airport
    # - **2** Daily transportation options (cars, scooters, taxis)
    # - **3** Estimated costs and booking tips

    return f"""
    🌅 **DAILY BREAKDOWN** (Provide {duration} full days)
    For each day, include:
    - **Morning Activity** (9-11 AM) with specific locations and times
    - **Afternoon Activity** (12-4 PM) with lunch suggestions
    - **Evening Activity** (5-8 PM) with dinner recommendations
    - **Evening Wind-down** (relaxation/beverages options)

    🏨 **HANDPICKED ACCOMMODATIONS**
    - **1** 2-3 specific hotel/villa recommendations with price ranges
    - **2** Location details and why they suit the traveler's interests
    - **3** Include both mid-range and premium options within budget

    🍜 **CULINARY EXPERIENCES**
    - **1** Daily restaurant recommendations for breakfast, lunch, dinner
    - **2** Must-try Balinese dishes with local specialties
    - **3** Food market or cooking class suggestions
    - **4** Beverage recommendations (non-alcoholic where appropriate)

    🎭 **CULTURAL IMMERSION**
    - **1** Local customs and etiquette tips
    - **2** Temple visit protocols if applicable
    - **3** Respectful photography guidelines

    ⭐ **AUTHENTIC EXPERIENCES**
    - **1** Unique local experiences not found in guidebooks
    - **2** Behind-the-scenes access opportunities
    - **3** Meet locals and community interactions
    - **4** Hidden gems based on their specific interests

    💸 **COMPREHENSIVE BUDGET BREAKDOWN**
    - **1** Daily spending estimates
    - **2** Total estimated cost vs. declared budget
    - **3** Cost-saving tips and premium upgrade options

    ⚡ **PRACTICAL INFORMATION**
    - **1** Best times to visit featured locations
    - **2** Weather considerations by season
    - **4** Emergency contacts
    """


def structure(duration: int, budget: str) -> str:
    """
    Itinerary structure analysis.

    Returns:
        A formatted itinerary structure string.
    """

    friendly_note = f"""
    ## 🌟 A Friendly Note

    This itinerary is a great starting point, but remember that details like opening hours and prices can change.
    We recommend double-checking before you go! For the most up-to-date information and to customize this plan with one of our experts,
    please contact us on WhatsApp at {WHATSAPP_NUMBER}. We'd love to help you create the perfect Bali journey
    """

    return f"""
    # 🌴 Here's your {duration}-Days Bali trip Itinerary with {budget} budget 🌴
    --title--
    ### 🌅 DAILY BREAKDOWN
    ## 🏨 HANDPICKED ACCOMMODATIONS
    ## 🍜 CULINARY EXPERIENCES
    ## 🎭 CULTURAL IMMERSION
    ## ⭐ AUTHENTIC EXPERIENCES
    ## 💸 COMPREHENSIVE BUDGET BREAKDOWN
    ## ⚡ PRACTICAL INFORMATION
    ## {friendly_note}
    """


def prompt(request: ItineraryRequestMD) -> str:
    """
    Create a detailed prompt for itinerary generation.

    Args:
        request: The itinerary request containing destination, duration, and interests.

    Returns:
        A formatted prompt string for the AI model.
    """

    interests = ", ".join(request.interests)
    duration = request.duration
    budget = request.budget

    return f"""
    Create a comprehensive and engaging {duration} day(s) travel itinerary for Bali.

    <traveler_profile>
    🎯 Interests: {interests}
    📅 Duration: {duration} day(s)
    💰 Budget: {budget}
    </traveler_profile>

    <title_instruction>
    Create a catchy, engaging title based on the traveler profile above.
    The title should:
    - Capture the essence of the trip in one memorable phrase
    - Include relevant emojis
    - Be concise (max 20 words)
    Example formats:
    - "## **🌴 Beach Bliss & Temple Trails: Your 5-Day Bali Escape 🌴**"
    - "## **🌊 Surf, Soul & Serenity: A Week in Paradise 🌊**"
    Place this title as a bold subtitle immediately after the main header.
    </title_instruction>

    <content_topics>
    {topics(duration)}
    </content_topics>

    <structure>
    Follow this exact markdown structure for your output:
    {structure(duration, budget)}
    </structure>

    <formatting_rules>
    - Follow proper markdown structure and headers usage
    - Use emojis liberally to make content engaging and easy to scan
    - Insert your creative title immediately after the main "# 🌴 Here's your..." header
    - For DAILY BREAKDOWN section, use #### (h4) for each day header (e.g., "#### **Day 1: ...**", "#### **Day 2: ...**")
    - Make sure no trailing spaces before any new line
    - Put a single newline character at the end of the document
    - Use bold text for important information (restaurant names, locations, prices)
    - Ensure each day has substantial content (at least 300-400 words each)
    - Total itinerary should be comprehensive enough for the traveler to execute
    </formatting_rules>

    Create a memorable, practical, and culturally rich Bali itinerary that exceeds expectations!
    """


async def generate_itinerary(
    request: Request,
    itinerary_req: ItineraryRequestMD,
    ai_client: AiClient,
) -> ItineraryMD:
    """
    Generate an itinerary based on the itinerary request.

    Args:
        request: The request object.
        itinerary_req: The itinerary request containing destination, duration, and interests.
        ai_client: The AI client to use for itinerary generation.

    Returns:
        A formatted itinerary string.
    """
    # will include "for {user name"} for future implementation from User database.
    logger.info(f"Generating itinerary from ip {host(request)}")

    result = await ai_client.do_service(
        contents=prompt(itinerary_req),
        system_instruction="You are an expert travel planner specializing in authentic Bali experiences.",
        resp_type=ItineraryMD,
        temperature=0.4,
    )
    response = cast(ItineraryMD, result)
    clean_md = await clean_markdown(response.itinerary, logger)
    # text_content = md_to_text(clean_md)

    # parent_dir = Path(__file__).parent
    # await save_to_file(clean_md, parent_dir / "ITINERARY.md")
    # await save_to_file(text_content, parent_dir / "ITINERARY.txt")
    return ItineraryMD(itinerary=clean_md)


async def ai_convert_txt(
    request: Request,
    itinerary_md: ItineraryRequestTXT,
    ai_client: AiClient,
) -> ItineraryTXT:
    """
    Ask ai to convert the itinerary to a text file.

    Args:
        request: The request object.
        itinerary_md: The itinerary markdown to convert request object.
        ai_client: The AI client to use for conversion.

    Returns:
        A formatted itinerary string.
    """

    system_instruction = """
    You are an expert on file conversion.
    Convert the input markdown file into a plain text file format.
    Create a proper text file that will send to WhatsApp that is easy to read and scan without losing the original content structure.
    """
    user_name = itinerary_md.user_name
    md_id = itinerary_md.md_id
    logger.info(
        f"Converting itinerary markdown for: user {user_name}, md_id: {md_id}, ip: {host(request)}",
    )

    result = await ai_client.do_service(
        contents=itinerary_md.itinerary_md,
        system_instruction=system_instruction,
        resp_type=ItineraryTXT,
        temperature=0.0,
    )

    return cast(ItineraryTXT, result)
