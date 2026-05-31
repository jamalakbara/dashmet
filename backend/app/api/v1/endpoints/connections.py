from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DbSession, OwnerUser
from app.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.schemas.accounts import ConnectionResponse, CreateConnectionRequest
from app.schemas.common import DataResponse
from app.services import accounts as acc_svc

router = APIRouter()


@router.get("")
def list_connections(current_user: CurrentUser, db: DbSession):
    conns = acc_svc.list_connections(db, current_user["org_id"])
    return DataResponse(
        data=[
            ConnectionResponse(
                id=str(c.id),
                platform=c.platform_id,
                is_active=c.is_active,
                scopes=c.scopes,
                token_type=c.token_type,
                connected_by=c.connected_by.name if c.connected_by else None,
                connected_at=c.created_at,
                last_used_at=c.last_used_at,
            )
            for c in conns
        ]
    )


@router.post("", status_code=201)
def create_connection(
    body: CreateConnectionRequest, current_user: OwnerUser, db: DbSession
):
    try:
        conn = acc_svc.create_connection(
            db,
            org_id=current_user["org_id"],
            user_id=current_user["user_id"],
            platform=body.platform,
            access_token=body.access_token,
            token_type=body.token_type,
        )
        db.commit()
        db.refresh(conn)

        from workers.tasks.structure import sync_accounts_for_connection
        sync_accounts_for_connection.delay(str(conn.id), current_user["org_id"])

        return DataResponse(
            data={
                "id": str(conn.id),
                "platform": conn.platform_id,
                "is_active": conn.is_active,
                "scopes": conn.scopes,
                "message": "Connection verified. Ad accounts are being imported.",
            }
        )
    except ConflictError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{connection_id}", status_code=204)
def delete_connection(connection_id: str, current_user: OwnerUser, db: DbSession):
    try:
        acc_svc.disconnect_connection(db, connection_id, current_user["org_id"])
        db.commit()
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
