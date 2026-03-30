from fastapi import Header, HTTPException

# API kluc - spolocny pre vsetky servisy
API_KEY = "5e5944fad25122ffa096ec690f0c547ebdb282342e822b60ba02fae86d3ef3e2"


def check_api_key(x_api_key: str = Header()):
    """Overi API kluc z hlavicky X-API-Key. Pouziva sa cez Depends(check_api_key)."""
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Neplatny API kluc")
