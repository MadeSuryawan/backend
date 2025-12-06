from pydantic import BaseModel, Field


class Activity(BaseModel):
    time: str = Field(description="Time of the activity, e.g., '09:00 AM'")
    description: str = Field(description="Description of the activity")
    location: str = Field(description="Location of the activity")
    tips: str | None = Field(default=None, description="Travel tips for this activity")


class DayPlan(BaseModel):
    day: int = Field(description="Day number")
    title: str = Field(description="Theme or title for the day")
    activities: list[Activity] = Field(description="List of activities for the day")


class Itinerary(BaseModel):
    trip_title: str = Field(description="A catchy title for the trip")
    destination: str = Field(description="Main destination of the trip")
    duration_days: int = Field(description="Duration of the trip in days")
    overview: str = Field(description="Brief overview of the entire trip")
    daily_plans: list[DayPlan] = Field(description="Daily itinerary details")
    estimated_cost: str | None = Field(default=None, description="Estimated cost range")
