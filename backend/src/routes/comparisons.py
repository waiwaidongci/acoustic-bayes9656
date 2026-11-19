from fastapi import APIRouter,Depends
from ..config.database import db_session
from ..schemas.comparison import ComparisonInput,AttributionInput
from ..services.auth import current_user,writer
from ..controllers.comparisons import ComparisonsController as C
router=APIRouter()
@router.get('/comparisons')
def comparisons(db=Depends(db_session),u=Depends(current_user)):return C.list(db)
@router.post('/comparisons')
def create(data:ComparisonInput,db=Depends(db_session),u=Depends(writer)):return C.create(db,u,data)
@router.get('/comparisons/{id}')
def detail(id:int,db=Depends(db_session),u=Depends(current_user)):return C.get(db,id)
@router.post('/comparisons/{id}/retry')
def retry(id:int,db=Depends(db_session),u=Depends(writer)):return C.retry(db,u,id)
@router.get('/sources/{id}/attributions')
def attributions(id:int,db=Depends(db_session),u=Depends(current_user)):return C.attributions(db,id)
@router.post('/sources/{id}/attributions')
def create_attribution(id:int,data:AttributionInput,db=Depends(db_session),u=Depends(writer)):return C.create_attribution(db,u,id,data)
