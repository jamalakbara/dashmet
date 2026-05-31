from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DbSession, OwnerUser
from app.exceptions import ConflictError, ForbiddenError, InvalidTokenError, NotFoundError
from app.schemas.common import DataResponse
from app.schemas.org import (
    AcceptInviteRequest,
    InviteRequest,
    MemberResponse,
    OrgResponse,
    OrgUpdateRequest,
)
from app.services import org as org_svc

router = APIRouter()


@router.get("")
def get_org(current_user: CurrentUser, db: DbSession):
    org = org_svc.get_org(db, current_user["org_id"])
    return DataResponse(
        data=OrgResponse(
            id=str(org.id),
            name=org.name,
            slug=org.slug,
            created_at=org.created_at,
        )
    )


@router.patch("")
def update_org(body: OrgUpdateRequest, current_user: OwnerUser, db: DbSession):
    org = org_svc.update_org(db, current_user["org_id"], body.name)
    db.commit()
    return DataResponse(
        data=OrgResponse(
            id=str(org.id),
            name=org.name,
            slug=org.slug,
            created_at=org.created_at,
        )
    )


@router.get("/members")
def list_members(current_user: CurrentUser, db: DbSession):
    members = org_svc.list_members(db, current_user["org_id"])
    return DataResponse(
        data=[
            MemberResponse(
                id=m["id"],
                name=m["name"],
                email=m["email"] or "",
                role=m["role"],
                joined_at=m["joined_at"],
                invite_pending=m["invite_pending"],
            )
            for m in members
        ]
    )


@router.post("/members/invite", status_code=201)
def invite_member(body: InviteRequest, current_user: OwnerUser, db: DbSession):
    try:
        mem = org_svc.invite_member(
            db,
            current_user["org_id"],
            current_user["user_id"],
            body.email,
            body.role,
        )
        db.commit()
        import logging
        logging.getLogger(__name__).info(
            f"[DEV] Invite token for {body.email}: {mem.invite_token}"
        )
        return DataResponse(data={"message": f"Invite sent to {body.email}"})
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/members/accept-invite")
def accept_invite(body: AcceptInviteRequest, db: DbSession):
    try:
        user, mem = org_svc.accept_invite(db, body.token, body.name, body.password)
        db.flush()

        from app.config import settings
        from app.services import auth as auth_svc

        token = auth_svc.create_access_token(
            str(user.id), str(mem.organization_id), mem.role, user.email
        )
        db.commit()

        from app.schemas.auth import TokenResponse
        return DataResponse(
            data=TokenResponse(
                access_token=token,
                token_type="bearer",
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            )
        )
    except InvalidTokenError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/members/{user_id}", status_code=204)
def remove_member(user_id: str, current_user: OwnerUser, db: DbSession):
    try:
        org_svc.remove_member(
            db,
            current_user["org_id"],
            user_id,
            current_user["user_id"],
        )
        db.commit()
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
