# app/models/trip.py
from pydantic import BaseModel, Field, validator, ConfigDict, field_validator
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Union
from enum import Enum
import uuid, json

class TripType(str, Enum):
    DOMESTIC = "domestic"
    INTERNATIONAL = "international"
    LOCAL = "local"

class TripStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class TransportType(str, Enum):
    FLIGHT = "flight"
    TRAIN = "train"
    BUS = "bus"
    CAR = "car"
    BIKE = "bike"
    WALK = "walk"

class ItineraryItem(BaseModel):
    day: int
    date: date
    activities: List[str]
    accommodation: Optional[str] = None
    meals: Optional[List[str]] = None
    transport: Optional[str] = None
    notes: Optional[str] = None

class FareBreakdown(BaseModel):
    transport_cost: float = 0.0
    accommodation_cost: float = 0.0
    meal_cost: float = 0.0
    activity_cost: float = 0.0
    guide_cost: float = 0.0
    misc_cost: float = 0.0
    service_charge: float = 0.0
    tax_amount: float = 0.0
    discount: float = 0.0

class TripCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    destination: str = Field(..., min_length=1, max_length=200)
    origin: Optional[str] = None
    trip_type: TripType
    start_date: date
    end_date: date
    duration_days: int = Field(..., gt=0)
    distance_km: Optional[float] = Field(None, ge=0)
    transport_type: TransportType
    number_of_travelers: int = Field(..., gt=0)
    description: Optional[str] = None
    itinerary: List[ItineraryItem]
    fare_breakdown: FareBreakdown
    total_amount: float = Field(..., gt=0)
    
    @validator('end_date')
    def validate_end_date(cls, v, values):
        if 'start_date' in values and v <= values['start_date']:
            raise ValueError('End date must be after start date')
        return v
    
    @validator('duration_days')
    def validate_duration(cls, v, values):
        if 'start_date' in values and 'end_date' in values:
            calculated_days = (values['end_date'] - values['start_date']).days + 1
            if v != calculated_days:
                raise ValueError('Duration days must match the date range')
        return v

# Also update your Pydantic model to handle serialization better
class TripUpdateRequest(BaseModel):
    title: Optional[str] = None
    destination: Optional[str] = None
    origin: Optional[str] = None
    trip_type: Optional[TripType] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    duration_days: Optional[int] = None
    distance_km: Optional[float] = None
    transport_type: Optional[TransportType] = None
    number_of_travelers: Optional[int] = None
    description: Optional[str] = None
    itinerary: Optional[List[ItineraryItem]] = None
    fare_breakdown: Optional[FareBreakdown] = None
    total_amount: Optional[float] = None
    status: Optional[TripStatus] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
        }
    
    def dict_with_json_strings(self, **kwargs):
        """Convert to dict with JSON-serialized complex fields"""
        data = self.dict(exclude_unset=True, **kwargs)
        
        # Convert complex fields to JSON strings
        if 'itinerary' in data and data['itinerary'] is not None:
            data['itinerary'] = json.dumps(
                [item.dict() if hasattr(item, 'dict') else item for item in data['itinerary']],
                default=_serialize_to_json
            )
        
        if 'fare_breakdown' in data and data['fare_breakdown'] is not None:
            data['fare_breakdown'] = json.dumps(
                data['fare_breakdown'].dict() if hasattr(data['fare_breakdown'], 'dict') else data['fare_breakdown'],
                default=_serialize_to_json
            )
        
        return data

class TripResponse(BaseModel):
    model_config = ConfigDict(
        # This allows the model to accept and convert compatible types
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=True
    )
    
    id: int
    trip_code: str
    title: str
    destination: str
    origin: Optional[str]
    trip_type: TripType
    status: TripStatus
    start_date: str
    end_date: str
    duration_days: int
    distance_km: Optional[float]
    transport_type: TransportType
    number_of_travelers: int
    description: Optional[str]
    itinerary: List[ItineraryItem]
    fare_breakdown: FareBreakdown
    total_amount: float
    user_id: Union[int, uuid.UUID]
    created_at: str
    updated_at: Optional[str]
    
    # Custom validators to handle type conversion
    @field_validator('start_date', 'end_date', mode='before')
    @classmethod
    def validate_dates(cls, v):
        if isinstance(v, date):
            return v.isoformat()
        elif isinstance(v, str):
            return v
        else:
            raise ValueError('Date must be a date object or string')
    
    @field_validator('created_at', 'updated_at', mode='before')
    @classmethod
    def validate_datetime(cls, v):
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        elif isinstance(v, str):
            return v
        else:
            raise ValueError('Datetime must be a datetime object or string')
    
    @field_validator('itinerary', mode='before')
    @classmethod
    def validate_itinerary(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                raise ValueError('Invalid JSON for itinerary')
        elif isinstance(v, list):
            return v
        else:
            raise ValueError('Itinerary must be a list or JSON string')
    
    @field_validator('fare_breakdown', mode='before')
    @classmethod
    def validate_fare_breakdown(cls, v):
        if isinstance(v, str):
            try:
                data = json.loads(v)
                return FareBreakdown(**data)
            except (json.JSONDecodeError, TypeError):
                raise ValueError('Invalid JSON for fare_breakdown')
        elif isinstance(v, dict):
            return FareBreakdown(**v)
        elif isinstance(v, FareBreakdown):
            return v
        else:
            raise ValueError('Fare breakdown must be a dict, FareBreakdown object, or JSON string')


class TripListResponse(BaseModel):
    trips: List[TripResponse]
    total: int
    page: int
    size: int
    total_pages: int
