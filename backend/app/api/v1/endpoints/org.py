import logging
import uuid

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DbSession, OwnerUser
from app.exceptions import ConflictError, ForbiddenError, InvalidTokenError, NotFoundError
from app.models.auth import User
from app.schemas.common import DataResponse
from app.schemas.org import (
    AcceptInviteRequest,
    InviteRequest,
    MemberResponse,
    OrgResponse,
    OrgUpdateRequest,
    SetMemberAccountsRequest,
)
from app.services import email as email_svc
from app.services import org as org_svc
from app.services.email import EmailError

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
                membership_id=m["membership_id"],
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
        invite_token = mem.invite_token
        db.commit()
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Send the email AFTER the invite row is committed: the invite exists
    # regardless of delivery outcome, and a delivery failure is reported
    # honestly rather than surfaced as a fake "sent".
    org = org_svc.get_org(db, current_user["org_id"])
    inviter = db.get(User, uuid.UUID(current_user["user_id"]))
    inviter_name = inviter.name if inviter else current_user["email"]
    try:
        sent = email_svc.send_invite_email(
            body.email, invite_token, org.name, inviter_name
        )
    except EmailError as e:
        logging.getLogger(__name__).error(
            "Invite email to %s failed: %s", body.email, e
        )
        sent = False

    message = (
        f"Invite sent to {body.email}"
        if sent
        else f"Invite created for {body.email}, but the email could not be sent."
    )
    return DataResponse(data={"message": message, "email_sent": sent})


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


@router.delete("/members/{membership_id}", status_code=204)
def remove_member(membership_id: str, current_user: OwnerUser, db: DbSession):
    try:
        org_svc.remove_member(
            db,
            current_user["org_id"],
            membership_id,
            current_user["user_id"],
        )
        db.commit()
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/members/{membership_id}/accounts")
def get_member_accounts(membership_id: str, current_user: OwnerUser, db: DbSession):
    try:
        ids = org_svc.list_member_accounts(db, current_user["org_id"], membership_id)
        return DataResponse(data={"account_ids": ids})
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/members/{membership_id}/accounts")
def set_member_accounts(
    membership_id: str,
    body: SetMemberAccountsRequest,
    current_user: OwnerUser,
    db: DbSession,
):
    try:
        ids = org_svc.set_member_accounts(
            db, current_user["org_id"], membership_id, body.account_ids
        )
        db.commit()
        return DataResponse(data={"account_ids": ids})
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid account id")
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
