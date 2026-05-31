from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict


class CampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform: str
    platform_campaign_id: str
    name: str
    status: str
    effective_status: str
    objective: Optional[str] = None
    daily_budget: Optional[Decimal] = None
    lifetime_budget: Optional[Decimal] = None
    buying_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_orm(cls, c) -> "CampaignResponse":
        return cls(
            id=str(c.id),
            platform=c.platform_id,
            platform_campaign_id=c.platform_campaign_id,
            name=c.name,
            status=c.status,
            effective_status=c.effective_status,
            objective=c.objective,
            daily_budget=c.daily_budget,
            lifetime_budget=c.lifetime_budget,
            buying_type=c.buying_type,
            start_date=c.start_date,
            end_date=c.end_date,
            created_at=c.created_at,
        )


class AdGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform_adgroup_id: str
    campaign_id: str
    name: str
    status: str
    effective_status: str
    optimization_goal: Optional[str] = None
    billing_event: Optional[str] = None
    bid_amount: Optional[Decimal] = None
    daily_budget: Optional[Decimal] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @classmethod
    def from_orm(cls, ag) -> "AdGroupResponse":
        return cls(
            id=str(ag.id),
            platform_adgroup_id=ag.platform_adgroup_id,
            campaign_id=str(ag.campaign_id),
            name=ag.name,
            status=ag.status,
            effective_status=ag.effective_status,
            optimization_goal=ag.optimization_goal,
            billing_event=ag.billing_event,
            bid_amount=ag.bid_amount,
            daily_budget=ag.daily_budget,
            start_date=ag.start_date,
            end_date=ag.end_date,
        )


class CreativePreview(BaseModel):
    title: Optional[str] = None
    thumbnail_url: Optional[str] = None
    format: Optional[str] = None
    cta_type: Optional[str] = None


class AdResponse(BaseModel):
    id: str
    platform_ad_id: str
    adgroup_id: str
    campaign_id: str
    name: str
    status: str
    effective_status: str
    has_creative: bool
    created_at: Optional[datetime] = None
    creative_preview: Optional[CreativePreview] = None

    @classmethod
    def from_orm(cls, ad) -> "AdResponse":
        preview = None
        if ad.creative:
            preview = CreativePreview(
                title=ad.creative.title,
                thumbnail_url=ad.creative.thumbnail_url,
                format=ad.creative.format,
                cta_type=ad.creative.cta_type,
            )
        return cls(
            id=str(ad.id),
            platform_ad_id=ad.platform_ad_id,
            adgroup_id=str(ad.ad_group_id),
            campaign_id=str(ad.campaign_id),
            name=ad.name,
            status=ad.status,
            effective_status=ad.effective_status,
            has_creative=ad.creative_id is not None,
            created_at=ad.created_at,
            creative_preview=preview,
        )


class CreativeResponse(BaseModel):
    id: str
    platform_creative_id: str
    format: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    video_id: Optional[str] = None
    cta_type: Optional[str] = None
    destination_url: Optional[str] = None
    synced_at: Optional[datetime] = None

    @classmethod
    def from_orm(cls, c) -> "CreativeResponse":
        return cls(
            id=str(c.id),
            platform_creative_id=c.platform_creative_id,
            format=c.format,
            title=c.title,
            body=c.body,
            image_url=c.image_url,
            thumbnail_url=c.thumbnail_url,
            video_id=c.video_id,
            cta_type=c.cta_type,
            destination_url=c.destination_url,
            synced_at=c.synced_at,
        )
