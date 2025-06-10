from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import scrape
import logging

logger = logging.getLogger("uvicorn.error")

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

@app.get("/bins", response_model=BinResponse)
async def get_bins(postcode: str, uprn: str):
    try:
        return scrape.get_bin_data(postcode, uprn)
    except scrape.ClientError as e:
        logging.exception(e)
        raise HTTPException(status_code=400, detail=str(e))
    except scrape.UpstreamError as e:
        logging.exception(e)
        raise HTTPException(status_code=503, detail=str(e))
    except scrape.ServiceUnavailableError as e:
        logging.exception(e)
        raise HTTPException(status_code=503, detail=str(e))
    except scrape.InvalidResponseError as e:
        logging.exception(e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logging.exception(e)
        raise HTTPException(status_code=500, detail=str(e))
