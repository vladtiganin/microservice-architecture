from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from sqlalchemy import Integer, String, Index, ForeignKey, Boolean, DateTime, func, Enum

from main_service.schemas.enums import WebhookDeliveryStatus
from main_service.models.job_models import Base


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"
    __table_args__ = (
        Index("idx_job_id", "job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), nullable=False)
    target_url: Mapped[str] = mapped_column(String(255), nullable=False)
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    delivery_status: Mapped[WebhookDeliveryStatus | None] = mapped_column(Enum(WebhookDeliveryStatus, name="webhook_delivery_status"), nullable=True)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
