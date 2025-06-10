from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from scrape import get_bin_data

app = FastAPI(
    title="Broxtowe Bin Collection API",
    description="API for retrieving bin collection data from Broxtowe Borough Council",
    version="1.0.0"
)

class BinData(BaseModel):
    type: str
    next_collection_raw: str
    next_collection_iso: str

class Address(BaseModel):
    uprn: str
    address: str

class BinResponse(BaseModel):
    bin_collections: Optional[List[BinData]]
    address: Address

class BinRequest(BaseModel):
    postcode: str
    uprn: str

@app.get("/")
async def root():
    return {"message": "Welcome to the Broxtowe Bin Collection API"}

@app.post("/bins", response_model=BinResponse)
async def get_bins(request: BinRequest):
    try:
        result = get_bin_data(request.postcode, request.uprn)
        if result is None:
            raise HTTPException(status_code=404, detail="No bin data found for the provided postcode and UPRN")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
