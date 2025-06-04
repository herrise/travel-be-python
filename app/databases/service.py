from typing import Optional, List, Tuple, Any, Dict
from datetime import datetime, timezone, date
import uuid
import asyncpg
from app.databases.postgres import fetchval, fetch, fetchrow, execute, run_transaction
from app.models.user import User, RefreshToken, UserRole, UserRegisterRequest, UserUpdateRequest, UserResponse
import logging
from app.models.trip import (
    TripCreateRequest, TripUpdateRequest, TripResponse, 
    TripListResponse, TripStatus, TripType, TripStatus, TransportType
)
import io
import secrets
import json
from decimal import Decimal
from enum import Enum



class DatabaseService:

    @staticmethod
    def _serialize_to_json(data):
        """Serialize data to JSON string with proper handling of complex types"""
        def convert_obj(obj):
            if isinstance(obj, (date, datetime)):
                return obj.isoformat()
            elif isinstance(obj, uuid.UUID):
                return str(obj)
            elif isinstance(obj, Decimal):
                return float(obj)
            elif isinstance(obj, Enum):
                return obj.value
            elif hasattr(obj, 'dict') and callable(getattr(obj, 'dict')):
                # Handle Pydantic models
                return obj.dict()
            elif hasattr(obj, '__dict__'):
                return obj.__dict__
            return obj
        
        try:
            # If it's a Pydantic model, use its dict() method
            if hasattr(data, 'dict') and callable(getattr(data, 'dict')):
                serializable_data = data.dict()
            elif hasattr(data, '__dict__'):
                serializable_data = data.__dict__
            else:
                serializable_data = data
            
            return json.dumps(serializable_data, default=convert_obj, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Error serializing data to JSON: {e}")
            raise

    @staticmethod
    def _parse_database_row_to_trip_response(row) -> TripResponse:
        """Convert database row to TripResponse format"""
        try:
            row_dict = dict(row)
            
            # Convert date and datetime objects to ISO strings
            if isinstance(row_dict.get('start_date'), date):
                row_dict['start_date'] = row_dict['start_date'].isoformat()
            if isinstance(row_dict.get('end_date'), date):
                row_dict['end_date'] = row_dict['end_date'].isoformat()
            if isinstance(row_dict.get('created_at'), datetime):
                row_dict['created_at'] = row_dict['created_at'].isoformat()
            if isinstance(row_dict.get('updated_at'), datetime):
                row_dict['updated_at'] = row_dict['updated_at'].isoformat()
            
            # Parse JSON strings back to objects
            if row_dict.get('itinerary'):
                if isinstance(row_dict['itinerary'], str):
                    row_dict['itinerary'] = json.loads(row_dict['itinerary'])
            else:
                row_dict['itinerary'] = []
                
            if row_dict.get('fare_breakdown'):
                if isinstance(row_dict['fare_breakdown'], str):
                    row_dict['fare_breakdown'] = json.loads(row_dict['fare_breakdown'])
            else:
                row_dict['fare_breakdown'] = {
                    "discount": 0.0,
                    "meal_cost": 0.0,
                    "accommodation_cost": 0.0
                }
            
            # Convert enum string values back to enum objects
            if isinstance(row_dict.get('trip_type'), str):
                row_dict['trip_type'] = TripType(row_dict['trip_type'])
            if isinstance(row_dict.get('status'), str):
                row_dict['status'] = TripStatus(row_dict['status'])
            if isinstance(row_dict.get('transport_type'), str):
                row_dict['transport_type'] = TransportType(row_dict['transport_type'])
            
            return TripResponse(**row_dict)
        except Exception as e:
            logging.error(f"Error parsing database row to TripResponse: {e}")
            raise
    
    # User operations
    @staticmethod
    async def create_user(user_data: UserRegisterRequest, password_hash: str) -> Optional[User]:
        """Create a new user"""
        query = """
            INSERT INTO public.users (email, username, password_hash, first_name, last_name)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, email, username, password_hash, first_name, last_name, 
                     role, is_active, is_verified, created_at, updated_at, last_login
        """
        try:
            record = await fetchrow(
                query, 
                user_data.email, 
                user_data.username, 
                password_hash,
                user_data.first_name,
                user_data.last_name
            )
            return User(**dict(record)) if record else None
        except asyncpg.UniqueViolationError as e:
            if "users_email_key" in str(e):
                raise ValueError("Email already registered")
            elif "users_username_key" in str(e):
                raise ValueError("Username already taken")
            else:
                raise ValueError("User already exists")
        except Exception as e:
            logging.error(f"Error creating user: {e}")
            raise
    
    @staticmethod
    async def get_user_by_email(email: str) -> Optional[User]:
        """Get user by email"""
        query = """
            SELECT id, email, username, password_hash, first_name, last_name,
                   role, is_active, is_verified, created_at, updated_at, last_login
            FROM public.users WHERE email = $1
        """
        record = await fetchrow(query, email)
        return User(**dict(record)) if record else None
    
    @staticmethod
    async def get_user_by_id(user_id: str) -> Optional[User]:
        """Get user by ID"""
        query = """
            SELECT id, email, username, password_hash, first_name, last_name,
                   role, is_active, is_verified, created_at, updated_at, last_login
            FROM public.users WHERE id = $1
        """
        record = await fetchrow(query, user_id)
        return User(**dict(record)) if record else None
    
    @staticmethod
    async def update_user_last_login(user_id: str) -> None:
        """Update user's last login timestamp"""
        query = "UPDATE users SET last_login = $1 WHERE id = $2"
        await execute(query, datetime.now(timezone.utc), uuid.UUID(user_id))
    
    @staticmethod
    async def get_all_users(page: int = 1, per_page: int = 20) -> Tuple[List[User], int]:
        """Get all users with pagination"""
        offset = (page - 1) * per_page
        
        # Get users
        query = """
            SELECT id, email, username, password_hash, first_name, last_name,
                   role, is_active, is_verified, created_at, updated_at, last_login
            FROM public.users 
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
        """
        records = await fetch(query, per_page, offset)
        users = [User(**dict(record)) for record in records]
        
        # Get total count
        count_query = "SELECT COUNT(*) FROM public.users"
        total_record = await fetchrow(count_query)
        total = total_record['count'] if total_record else 0
        
        return users, total
    
    @staticmethod
    async def update_user(user_id: str, update_data: UserUpdateRequest) -> Optional[User]:
        """Update user"""
        # Build dynamic query
        updates = []
        params = []
        param_count = 1
        
        if update_data.first_name is not None:
            updates.append(f"first_name = ${param_count}")
            params.append(update_data.first_name)
            param_count += 1
            
        if update_data.last_name is not None:
            updates.append(f"last_name = ${param_count}")
            params.append(update_data.last_name)
            param_count += 1
            
        if update_data.role is not None:
            updates.append(f"role = ${param_count}")
            params.append(update_data.role.value)
            param_count += 1
            
        if update_data.is_active is not None:
            updates.append(f"is_active = ${param_count}")
            params.append(update_data.is_active)
            param_count += 1
            
        if update_data.is_verified is not None:
            updates.append(f"is_verified = ${param_count}")
            params.append(update_data.is_verified)
            param_count += 1
        
        if not updates:
            return await DatabaseService.get_user_by_id(user_id)
        
        updates.append(f"updated_at = ${param_count}")
        params.append(datetime.now(timezone.utc))
        param_count += 1
        
        params.append(uuid.UUID(user_id))
        
        query = f"""
            UPDATE users 
            SET {', '.join(updates)}
            WHERE id = ${param_count}
            RETURNING id, email, username, password_hash, first_name, last_name,
                     role, is_active, is_verified, created_at, updated_at, last_login
        """
        
        record = await fetchrow(query, *params)
        return User(**dict(record)) if record else None
    
    # Refresh token operations
    @staticmethod
    async def create_refresh_token(
        user_id: str, 
        token_hash: str, 
        expires_at: datetime,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> str:
        """Create refresh token"""
        token_id = uuid.uuid4()
        query = """
            INSERT INTO public.refresh_tokens (id, user_id, token_hash, expires_at, user_agent, ip_address)
            VALUES ($1, $2, $3, $4, $5, $6)
        """
        await execute(query, token_id, uuid.UUID(user_id), token_hash, expires_at, user_agent, ip_address)
        return str(token_id)
    
    @staticmethod
    async def get_refresh_token_by_hash(token_hash: str) -> Optional[RefreshToken]:
        """Get refresh token by hash"""
        query = """
            SELECT id, user_id, token_hash, expires_at, is_revoked, created_at, user_agent, ip_address
            FROM public.refresh_tokens 
            WHERE token_hash = $1 AND is_revoked = false AND expires_at > $2
        """
        record = await fetchrow(query, token_hash, datetime.now(timezone.utc))
        return RefreshToken(**dict(record)) if record else None
    
    
    @staticmethod
    async def cleanup_expired_tokens() -> None:
        """Clean up expired tokens"""
        current_time = datetime.now(timezone.utc)
        queries = [
            ("DELETE FROM public.refresh_tokens WHERE expires_at < $1", (current_time,)),
            ("DELETE FROM public.blacklisted_tokens WHERE expires_at < $1", (current_time,)),
            ("DELETE FROM public.user_sessions WHERE expires_at < $1", (current_time,))
        ]
        await run_transaction(queries)
    
    
    
    # User session operations (optional)
    @staticmethod
    async def create_user_session(
        user_id: str,
        session_token: str,
        expires_at: datetime,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> str:
        """Create user session"""
        session_id = uuid.uuid4()
        query = """
            INSERT INTO public.user_sessions (id, user_id, session_token, expires_at, user_agent, ip_address)
            VALUES ($1, $2, $3, $4, $5, $6)
        """
        await execute(query, session_id, uuid.UUID(user_id), session_token, expires_at, user_agent, ip_address)
        return str(session_id)
    
    @staticmethod
    async def get_user_active_sessions(user_id: str) -> List[dict]:
        """Get user's active sessions"""
        query = """
            SELECT id, session_token, created_at, last_accessed, user_agent, ip_address
            FROM public.user_sessions 
            WHERE user_id = $1 AND is_active = true AND expires_at > $2
            ORDER BY last_accessed DESC
        """
        records = await fetch(query, uuid.UUID(user_id), datetime.now(timezone.utc))
        return [dict(record) for record in records]
    
    @staticmethod
    async def revoke_user_session(session_id: str) -> None:
        """Revoke user session"""
        query = "UPDATE user_sessions SET is_active = false WHERE id = $1"
        await execute(query, uuid.UUID(session_id))

    @staticmethod
    async def revoke_refresh_token(token_id: str):
        """Revoke a specific refresh token"""
        from app.databases.postgres import execute
        query = "UPDATE refresh_tokens SET is_revoked = true WHERE id = $1"
        await execute(query, token_id)
    
    @staticmethod
    async def revoke_all_user_refresh_tokens(user_id: str):
        """Revoke all refresh tokens for a user"""
        from app.databases.postgres import execute
        query = "UPDATE refresh_tokens SET is_revoked = true WHERE user_id = $1"
        await execute(query, user_id)

    @staticmethod
    async def is_token_blacklisted(jti: str) -> bool:
        """Check if a token JTI is blacklisted"""
        try:
            result = await fetchval(
                "SELECT EXISTS(SELECT 1 FROM blacklisted_tokens WHERE jti = $1)",
                jti
            )
            return bool(result)
        except Exception as e:
            logging.error(f"Error checking token blacklist: {e}")
            # In case of error, assume token is blacklisted for security
            return True
    
    @staticmethod
    async def blacklist_token(jti: str, expires_at: Optional[datetime] = None) -> bool:
        """Add a token to the blacklist"""
        try:
            await execute(
                """
                INSERT INTO blacklisted_tokens (jti, blacklisted_at, expires_at) 
                VALUES ($1, NOW(), $2)
                ON CONFLICT (jti) DO NOTHING
                """,
                jti, expires_at
            )
            return True
        except Exception as e:
            logging.error(f"Error blacklisting token: {e}")
            return False
    
    async def create_trip(user_id: int, trip_data: TripCreateRequest) -> Optional[TripResponse]:
        """Create a new trip"""
        try:
            # Generate unique trip code
            trip_code = f"TR{datetime.now().strftime('%Y%m%d')}{secrets.token_hex(4).upper()}"
            
            # Convert complex data to JSON strings using helper method
            itinerary_json = DatabaseService._serialize_to_json(trip_data.itinerary)
            fare_breakdown_json = DatabaseService._serialize_to_json(trip_data.fare_breakdown)
            
            row = await fetchrow(
                """
                INSERT INTO trips (
                    trip_code, title, destination, origin, trip_type, status,
                    start_date, end_date, duration_days, distance_km, transport_type,
                    number_of_travelers, description, itinerary, fare_breakdown,
                    total_amount, user_id, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, NOW())
                RETURNING *
                """,
                trip_code, trip_data.title, trip_data.destination, trip_data.origin,
                trip_data.trip_type.value, TripStatus.DRAFT.value, trip_data.start_date,
                trip_data.end_date, trip_data.duration_days, trip_data.distance_km,
                trip_data.transport_type.value, trip_data.number_of_travelers,
                trip_data.description, itinerary_json, 
                fare_breakdown_json, trip_data.total_amount, user_id
            )
            
            if row:
                return DatabaseService._parse_database_row_to_trip_response(row)
            return None
        except Exception as e:
            logging.error(f"Error creating trip: {e}")
            return None


    @staticmethod
    async def get_user_trips(
        user_id: int, 
        page: int = 1, 
        size: int = 10,
        status: Optional[TripStatus] = None
    ) -> Optional[TripListResponse]:
        """Get trips for a specific user"""
        try:
            offset = (page - 1) * size
            
            where_clause = "WHERE user_id = $1"
            params = [user_id]
            
            if status:
                where_clause += " AND status = $2"
                params.append(status.value)
            
            # Get total count
            total_query = f"SELECT COUNT(*) FROM trips {where_clause}"
            total = await fetchval(total_query, *params)
            
            # Get trips
            trips_query = f"""
                SELECT * FROM trips {where_clause}
                ORDER BY created_at DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """
            params.extend([size, offset])
            
            rows = await fetch(trips_query, *params)
            
            # Convert database rows to proper format for Pydantic
            trips = []
            for row in rows:
                trip_data = dict(row)
                
                # Convert datetime objects to ISO strings
                if trip_data.get('start_date'):
                    trip_data['start_date'] = trip_data['start_date'].isoformat()
                if trip_data.get('end_date'):
                    trip_data['end_date'] = trip_data['end_date'].isoformat()
                if trip_data.get('created_at'):
                    trip_data['created_at'] = trip_data['created_at'].isoformat()
                if trip_data.get('updated_at'):
                    trip_data['updated_at'] = trip_data['updated_at'].isoformat()
                
                # Parse JSON strings to proper objects
                if trip_data.get('itinerary') and isinstance(trip_data['itinerary'], str):
                    try:
                        trip_data['itinerary'] = json.loads(trip_data['itinerary'])
                    except json.JSONDecodeError:
                        trip_data['itinerary'] = []
                
                if trip_data.get('fare_breakdown') and isinstance(trip_data['fare_breakdown'], str):
                    try:
                        trip_data['fare_breakdown'] = json.loads(trip_data['fare_breakdown'])
                    except json.JSONDecodeError:
                        trip_data['fare_breakdown'] = {}
                
                trips.append(TripResponse(**trip_data))
            
            total_pages = (total + size - 1) // size
            
            return TripListResponse(
                trips=trips,
                total=total,
                page=page,
                size=size,
                total_pages=total_pages
            )
        except Exception as e:
            logging.error(f"Error fetching user trips: {e}")
            return None

    async def get_trip_by_code(trip_code: str, user_id: Optional[int] = None) -> Optional[TripResponse]:
        """Get trip by ID with proper data conversion"""
        try:
            where_clause = "WHERE trip_code = $1"
            params = [trip_code]
            
            if user_id is not None:
                where_clause += " AND user_id = $2"
                params.append(user_id)
            
            row = await fetchrow(f"SELECT * FROM trips {where_clause}", *params)
            
            if row:
                # Convert row to dict and handle data types
                trip_data = dict(row)
                
                # Convert dates to strings if they're date objects
                if isinstance(trip_data.get('start_date'), date):
                    trip_data['start_date'] = trip_data['start_date'].isoformat()
                if isinstance(trip_data.get('end_date'), date):
                    trip_data['end_date'] = trip_data['end_date'].isoformat()
                
                # Convert datetime to string if it's a datetime object
                if isinstance(trip_data.get('created_at'), datetime):
                    trip_data['created_at'] = trip_data['created_at'].isoformat()
                if isinstance(trip_data.get('updated_at'), datetime):
                    trip_data['updated_at'] = trip_data['updated_at'].isoformat()
                
                # Parse JSON strings if needed
                if isinstance(trip_data.get('itinerary'), str):
                    try:
                        trip_data['itinerary'] = json.loads(trip_data['itinerary'])
                    except json.JSONDecodeError:
                        trip_data['itinerary'] = []
                
                if isinstance(trip_data.get('fare_breakdown'), str):
                    try:
                        trip_data['fare_breakdown'] = json.loads(trip_data['fare_breakdown'])
                    except json.JSONDecodeError:
                        trip_data['fare_breakdown'] = {}
                
                # Use model_validate instead of direct instantiation
                return TripResponse.model_validate(trip_data)
            return None
        except Exception as e:
            logging.error(f"Error fetching trip: {e}")
            return None

    
    @staticmethod
    async def update_trip(trip_code: str, user_id: int, updates: TripUpdateRequest) -> Optional[TripResponse]:
        """Update trip"""
        try:
            set_clauses = []
            params = []
            param_count = 1
            
            for field, value in updates.dict(exclude_unset=True).items():
                if value is not None:
                    # Handle JSON fields properly
                    if field in ['itinerary', 'fare_breakdown']:
                        try:
                            # Use the existing _serialize_to_json method
                            value = DatabaseService._serialize_to_json(value)
                        except Exception as e:
                            logging.error(f"Error serializing {field}: {e}")
                            continue
                    elif hasattr(value, 'value'):
                        # Handle enum values
                        value = value.value
                    
                    set_clauses.append(f"{field} = ${param_count}")
                    params.append(value)
                    param_count += 1
            
            if not set_clauses:
                return await DatabaseService.get_trip_by_code(trip_code, user_id)
            
            # Add updated_at timestamp
            set_clauses.append(f"updated_at = ${param_count}")
            params.append(datetime.utcnow())
            param_count += 1
            
            # Add WHERE clause parameters
            params.extend([trip_code, user_id])
            
            query = f"""
                UPDATE trips 
                SET {', '.join(set_clauses)}
                WHERE trip_code = ${param_count} AND user_id = ${param_count + 1}
                RETURNING *
            """
            
            row = await fetchrow(query, *params)
            if row:
                return TripResponse(**dict(row))
            return None
        except Exception as e:
            logging.error(f"Error updating trip: {e}")
            return None

    @staticmethod
    async def delete_trip(trip_code: str, user_id: int) -> bool:
        """Delete trip"""
        try:
            result = await execute(
                "DELETE FROM trips WHERE trip_code = $1 AND user_id = $2",
                trip_code, user_id
            )
            return "DELETE 1" in result
        except Exception as e:
            logging.error(f"Error deleting trip: {e}")
            return False

    @staticmethod
    async def get_revenue_report(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """Generate revenue report"""
        try:
            where_clause = "WHERE status = 'completed'"
            params = []
            
            if start_date:
                where_clause += f" AND created_at >= ${len(params) + 1}"
                params.append(start_date)
            
            if end_date:
                where_clause += f" AND created_at <= ${len(params) + 1}"
                params.append(end_date)
            
            # Total revenue
            total_revenue = await fetchval(
                f"SELECT COALESCE(SUM(total_amount), 0) FROM trips {where_clause}",
                *params
            )
            
            # Trip count
            trip_count = await fetchval(
                f"SELECT COUNT(*) FROM trips {where_clause}",
                *params
            )
            
            # Average trip value
            avg_trip_value = await fetchval(
                f"SELECT COALESCE(AVG(total_amount), 0) FROM trips {where_clause}",
                *params
            )
            
            # Revenue by trip type
            revenue_by_type = await fetch(
                f"""
                SELECT trip_type, COUNT(*) as trip_count, SUM(total_amount) as total_revenue
                FROM trips {where_clause}
                GROUP BY trip_type
                ORDER BY total_revenue DESC
                """,
                *params
            )
            
            return {
                "total_revenue": float(total_revenue),
                "trip_count": trip_count,
                "average_trip_value": float(avg_trip_value),
                "revenue_by_type": [dict(row) for row in revenue_by_type],
                "period": {
                    "start_date": start_date,
                    "end_date": end_date
                }
            }
        except Exception as e:
            logging.error(f"Error generating revenue report: {e}")
            return {
                "total_revenue": 0,
                "trip_count": 0,
                "average_trip_value": 0,
                "revenue_by_type": [],
                "error": str(e)
            }

    @staticmethod
    async def get_all_trips(
        page: int = 1, 
        size: int = 10, 
        status: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get all trips for admin"""
        try:
            offset = (page - 1) * size
            
            where_clause = ""
            params = []
            
            if status:
                where_clause = "WHERE status = $1"
                params.append(status)
            
            # Get total count
            total_query = f"SELECT COUNT(*) FROM trips {where_clause}"
            total = await fetchval(total_query, *params)
            
            # Get trips
            trips_query = f"""
                SELECT t.*, u.email as user_email, u.first_name, u.last_name
                FROM trips t
                JOIN users u ON t.user_id = u.id
                {where_clause}
                ORDER BY t.created_at DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """
            params.extend([size, offset])
            
            rows = await fetch(trips_query, *params)
            
            trips = []
            for row in rows:
                from app.models.trip import TripResponse, ItineraryItem, FareBreakdown
                row_dict = dict(row)
                
                # Parse JSON fields
                if row_dict['itinerary']:
                    itinerary_data = json.loads(row_dict['itinerary']) if isinstance(row_dict['itinerary'], str) else row_dict['itinerary']
                    row_dict['itinerary'] = [ItineraryItem(**item) for item in itinerary_data]
                
                if row_dict['fare_breakdown']:
                    fare_data = json.loads(row_dict['fare_breakdown']) if isinstance(row_dict['fare_breakdown'], str) else row_dict['fare_breakdown']
                    row_dict['fare_breakdown'] = FareBreakdown(**fare_data)
                
                # Remove extra fields
                row_dict.pop('user_email', None)
                row_dict.pop('first_name', None)
                row_dict.pop('last_name', None)
                
                trips.append(TripResponse(**row_dict))
            
            total_pages = (total + size - 1) // size
            
            return {
                "trips": trips,
                "total": total,
                "page": page,
                "size": size,
                "total_pages": total_pages
            }
        except Exception as e:
            logging.error(f"Error fetching all trips: {e}")
            return None

    @staticmethod
    async def admin_update_user(user_id: str, updates: Dict[str, Any]) -> Optional[UserResponse]:
        """Update user by admin"""
        try:
            set_clauses = []
            params = []
            param_count = 1
            
            allowed_fields = ['email', 'username', 'first_name', 'last_name', 'role', 'is_active', 'is_verified']
            
            for field, value in updates.items():
                if field in allowed_fields and value is not None:
                    set_clauses.append(f"{field} = ${param_count}")
                    params.append(value)
                    param_count += 1
            
            if not set_clauses:
                return await DatabaseService.get_user_response_by_id(user_id)
            
            set_clauses.append(f"updated_at = ${param_count}")
            params.append(datetime.utcnow())
            params.append(user_id)
            
            query = f"""
                UPDATE users 
                SET {', '.join(set_clauses)}
                WHERE id = ${param_count + 1}
                RETURNING id, email, username, first_name, last_name, role, 
                         is_active, is_verified, created_at, updated_at, last_login
            """
            
            row = await fetchrow(query, *params)
            if row:
                return UserResponse(**dict(row))
            return None
        except Exception as e:
            logging.error(f"Error updating user: {e}")
            return None


    @staticmethod
    async def update_user_status(user_id: str, is_active: bool) -> bool:
        """Update user active status"""
        try:
            result = await execute(
                "UPDATE users SET is_active = $1, updated_at = NOW() WHERE id = $2",
                is_active, user_id
            )
            return "UPDATE 1" in result
        except Exception as e:
            logging.error(f"Error updating user status: {e}")
            return False


    @staticmethod
    async def get_user_response_by_id(user_id: str) -> Optional[UserResponse]:
        """Get user response by ID"""
        try:
            row = await fetchrow(
                """
                SELECT id, email, username, first_name, last_name, role, 
                       is_active, is_verified, created_at, updated_at, last_login 
                FROM users 
                WHERE id = $1
                """,
                user_id
            )
            if row:
                return UserResponse(**dict(row))
            return None
        except Exception as e:
            logging.error(f"Error fetching user response by ID: {e}")
            return None


    @staticmethod
    async def get_admin_stats() -> Dict[str, Any]:
        """Get admin dashboard statistics"""
        try:
            # Total users
            total_users = await fetchval("SELECT COUNT(*) FROM users")
            
            # Active users
            active_users = await fetchval("SELECT COUNT(*) FROM users WHERE is_active = true")
            
            # Total trips
            total_trips = await fetchval("SELECT COUNT(*) FROM trips")
            
            # Completed trips
            completed_trips = await fetchval("SELECT COUNT(*) FROM trips WHERE status = 'completed'")
            
            # Total revenue
            total_revenue = await fetchval(
                "SELECT COALESCE(SUM(total_amount), 0) FROM trips WHERE status = 'completed'"
            )
            
            # Recent trips (last 7 days)
            recent_trips = await fetchval(
                "SELECT COUNT(*) FROM trips WHERE created_at >= NOW() - INTERVAL '7 days'"
            )
            
            return {
                "total_users": total_users,
                "active_users": active_users,
                "total_trips": total_trips,
                "completed_trips": completed_trips,
                "total_revenue": float(total_revenue) if total_revenue else 0,
                "recent_trips": recent_trips
            }
        except Exception as e:
            logging.error(f"Error fetching admin stats: {e}")
            raise