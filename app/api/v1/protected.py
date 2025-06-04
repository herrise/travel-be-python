from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from typing import Dict, Any, List, Optional
import math

from app.models.user import (
    MessageResponse, AdminUserListResponse, UserResponse, 
    UserUpdateRequest, UserRole
)
from app.utils.auth import get_current_user, require_admin, get_current_active_user
from app.databases.service import DatabaseService
from app.models.trip import (
    TripCreateRequest, TripUpdateRequest, TripResponse, 
    TripListResponse, TripStatus
)
from app.services.pdf_service import PDFService
from fastapi.responses import StreamingResponse
import io
from datetime import datetime


router = APIRouter()


# @router.get("/admin/users", response_model=AdminUserListResponse)
# async def get_all_users(
#     page: int = Query(1, ge=1, description="Page number"),
#     per_page: int = Query(20, ge=1, le=100, description="Items per page"),
#     admin_user: Dict[str, Any] = Depends(require_admin)
# ):
#     """Admin route - Get all users with pagination"""
#     try:
#         users, total = await DatabaseService.get_all_users(page, per_page)
        
#         user_responses = [
#             UserResponse(
#                 id=user.id,
#                 email=user.email,
#                 username=user.username,
#                 first_name=user.first_name,
#                 last_name=user.last_name,
#                 role=user.role,
#                 is_active=user.is_active,
#                 is_verified=user.is_verified,
#                 created_at=user.created_at,
#                 updated_at=user.updated_at,
#                 last_login=user.last_login
#             )
#             for user in users
#         ]
        
#         pages = math.ceil(total / per_page) if total > 0 else 1
        
#         return AdminUserListResponse(
#             users=user_responses,
#             total=total,
#             page=page,
#             per_page=per_page,
#             pages=pages
#         )
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to fetch users"
#         )

# @router.get("/admin/stats", response_model=Dict[str, Any])
# async def get_admin_stats(admin_user: Dict[str, Any] = Depends(require_admin)):
#     """Admin route - Get system statistics"""
#     try:
#         # Get total users
#         all_users, total_users = await DatabaseService.get_all_users(1, 1)
        
#         # You can add more statistics here
#         # For example: active users, users by role, etc.
        
#         return {
#             "total_users": total_users,
#             "admin_user": admin_user["username"],
#             "timestamp": "2024-01-01T00:00:00Z"  # You can use datetime.now()
#         }
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to fetch statistics"
#         )

# Add the admin stats endpoint
@router.get("/admin/stats")
async def get_admin_stats(current_user: UserResponse = Depends(require_admin)):
    """Get admin statistics"""
    try:
        # Get basic stats
        stats = await DatabaseService.get_admin_stats()
        return {
            "stats": stats,
            "admin_user": {
                "id": current_user.id,
                "email": current_user.email,
                "role": current_user.role
            }
        }
    except Exception as e:
        logging.error(f"Error fetching admin stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch stats: {str(e)}"
        )

@router.post("/admin/cleanup", response_model=MessageResponse)
async def cleanup_expired_tokens(admin_user: Dict[str, Any] = Depends(require_admin)):
    """Admin route - Clean up expired tokens"""
    try:
        await DatabaseService.cleanup_expired_tokens()
        return MessageResponse(message="Expired tokens cleaned up successfully")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cleanup tokens"
        )

@router.get("/")
async def protected_root(current_user: UserResponse = Depends(get_current_active_user)):
    """Basic protected route"""
    return {
        "message": "Hello from protected route!",
        "user": current_user.email,
        "timestamp": datetime.utcnow()
    }

@router.get("/profile", response_model=UserResponse)
async def get_profile(current_user: UserResponse = Depends(get_current_active_user)):
    """Get user profile"""
    return current_user

# Trip Management Routes
@router.post("/trips", response_model=TripResponse)
async def create_trip(
    trip_data: TripCreateRequest,
    current_user: UserResponse = Depends(get_current_active_user)
):
    """Create a new trip"""
    trip = await DatabaseService.create_trip(current_user.id, trip_data)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create trip"
        )
    return trip

@router.get("/trips", response_model=TripListResponse)
async def get_my_trips(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    status: Optional[TripStatus] = None,
    current_user: UserResponse = Depends(get_current_active_user)
):
    """Get user's trips"""
    trips = await DatabaseService.get_user_trips(current_user.id, page, size, status)
    if trips is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch trips"
        )
    return trips


@router.get("/trips/{trip_code}", response_model=TripResponse)
async def get_trip(
    trip_code: str,
    current_user: UserResponse = Depends(get_current_active_user)
):
    """Get specific trip"""
    trip = await DatabaseService.get_trip_by_code(trip_code, current_user.id)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )
    return trip

@router.put("/trips/{trip_code}", response_model=TripResponse)
async def update_trip(
    trip_code: str,
    trip_data: TripUpdateRequest,
    current_user: UserResponse = Depends(get_current_active_user)
):
    """Update trip"""
    trip = await DatabaseService.update_trip(trip_code, current_user.id, trip_data)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found or failed to update"
        )
    return trip

@router.delete("/trips/{trip_code}")
async def delete_trip(
    trip_code: str,
    current_user: UserResponse = Depends(get_current_active_user)
):
    """Delete trip"""
    success = await DatabaseService.delete_trip(trip_code, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found or failed to delete"
        )
    return {"message": "Trip deleted successfully"}

# PDF Invoice Generation
@router.get("/trips/{trip_code}/invoice")
async def generate_trip_invoice(
    trip_code: str,
    current_user: UserResponse = Depends(get_current_active_user)
):
    """Generate PDF invoice for a trip"""
    trip = await DatabaseService.get_trip_by_code(trip_code, current_user.id)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )
    
    try:
        pdf_content = PDFService.generate_trip_invoice(trip, current_user)
        
        return StreamingResponse(
            io.BytesIO(pdf_content),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=invoice_{trip.trip_code}.pdf"
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate invoice: {str(e)}"
        )

@router.get("/trips/{trip_code}/report")
async def generate_trip_report(
    trip_code: str,
    current_user: UserResponse = Depends(get_current_active_user)
):
    """Generate detailed trip report"""
    trip = await DatabaseService.get_trip_by_code(trip_code, current_user.id)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )
    
    try:
        pdf_content = PDFService.generate_trip_invoice(trip, current_user)  # Can be extended for detailed report
        
        return StreamingResponse(
            io.BytesIO(pdf_content),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=report_{trip.trip_code}.pdf"
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate report: {str(e)}"
        )

# Admin Routes
@router.get("/admin/users", dependencies=[Depends(require_admin)])
async def list_all_users(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100)
):
    """List all users (admin only)"""
    users = await DatabaseService.get_all_users(page, size)
    if users is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch users"
        )
    return users

@router.get("/admin/users/{user_id}", dependencies=[Depends(require_admin)])
async def get_user_by_id(user_id: str):
    """Get specific user (admin only)"""
    user = await DatabaseService.get_user_by_id(str(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user

@router.put("/admin/users/{user_id}", dependencies=[Depends(require_admin)])
async def update_user(user_id: str, updates: dict):
    """Update user (admin only)"""
    user = await DatabaseService.admin_update_user(user_id, updates)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or failed to update"
        )
    return user

@router.post("/admin/users/{user_id}/activate", dependencies=[Depends(require_admin)])
async def activate_user(user_id: str):
    """Activate user (admin only)"""
    success = await DatabaseService.update_user_status(user_id, True)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or failed to activate"
        )
    return {"message": "User activated successfully"}

@router.post("/admin/users/{user_id}/deactivate", dependencies=[Depends(require_admin)])
async def deactivate_user(user_id: str):
    """Deactivate user (admin only)"""
    success = await DatabaseService.update_user_status(user_id, False)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or failed to deactivate"
        )
    return {"message": "User deactivated successfully"}

@router.get("/admin/trips", dependencies=[Depends(require_admin)])
async def get_all_trips(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    status: Optional[TripStatus] = None
):
    """Get all trips across all users (admin only)"""
    trips = await DatabaseService.get_all_trips(page, size, status)
    if trips is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch trips"
        )
    return trips

@router.get("/admin/reports/revenue")
async def get_revenue_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: UserResponse = Depends(require_admin)
):
    """Generate revenue report (admin only)"""
    report = await DatabaseService.get_revenue_report(start_date, end_date)
    return report