# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import (
    auth_service,
    catalog_service,
    booking_service,
    customer_service,
    orders_service,
    coupon_service,
    admin_service,
    admin_manage,
)

app = FastAPI(title="UNISEX Salon Microservices")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_service.router)
app.include_router(catalog_service.router)
app.include_router(booking_service.router)
app.include_router(customer_service.router)
app.include_router(orders_service.router)
app.include_router(coupon_service.router)
app.include_router(admin_service.router)
app.include_router(admin_manage.router)