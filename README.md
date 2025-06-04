"""
pip install fastapi python-jose[cryptography] passlib[bcrypt] python-multipart uvicorn

Project Structure:
├── main.py                 # FastAPI app entry point
├── api/
│   ├── __init__.py
│   └── v1/
│       ├── __init__.py
│       ├── auth.py         # Authentication endpoints
│       └── protected.py    # Protected routes
├── models/
│   ├── __init__.py
│   └── user.py            # Pydantic models
├── core/
│   ├── __init__.py
│   ├── config.py          # App configuration
│   └── security.py        # Security utilities
└── dependencies/
    ├── __init__.py
    └── auth.py            # Authentication dependencies

Run the application:
uvicorn main:app --reload

API Endpoints:
- POST /api/v1/auth/register    - Register new user
- POST /api/v1/auth/login       - User login
- POST /api/v1/auth/refresh     - Refresh token
- POST /api/v1/auth/logout      - User logout
- GET  /api/v1/auth/me          - Get current user
- GET  /api/v1/protected/       - Protected route
- GET  /api/v1/protected/admin/users - Admin route

Example Usage:
1. Register: POST /api/v1/auth/register
2. Login: POST /api/v1/auth/login
3. Use token: Authorization: Bearer <token>
"""