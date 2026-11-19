from pydantic import BaseModel,Field
class AttributionInput(BaseModel):
    mapping:dict[str,str]=Field(min_length=1)
    note:str=Field(default='',max_length=200)
class ComparisonInput(BaseModel):
    run_a_id:int
    run_b_id:int
    fault_a:str=Field(min_length=1,max_length=120)
    fault_b:str=Field(min_length=1,max_length=120)
    name:str=Field(default='',max_length=160)
    attribution_version:int|None=None
    samples:int|None=None
