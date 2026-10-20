from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session
from app.core.deps import get_db, require_merchant
from app.models.tables import User
from app.agent.product_actions import ProductProposal, owned_proposal, snapshot, confirm_proposal

router = APIRouter(prefix="/b/agent/product-proposals", tags=["agent-actions"])

@router.get("/{proposal_id}")
def read_proposal(proposal_id: str, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return snapshot(owned_proposal(db, user, proposal_id))

@router.post("/{proposal_id}/confirm")
def confirm(proposal_id: str, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return confirm_proposal(db, user, proposal_id)

@router.post("/{proposal_id}/cancel")
def cancel(proposal_id: str, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    proposal = owned_proposal(db, user, proposal_id)
    changed = db.execute(update(ProductProposal).where(ProductProposal.id == proposal.id,
        ProductProposal.status == "pending").values(status="cancelled"))
    db.commit()
    db.refresh(proposal)
    if not changed.rowcount and proposal.status != "cancelled":
        raise HTTPException(409, "提案已执行，无法取消；请在商品管理中处理草稿")
    return snapshot(proposal)
