# =============================================================================
# AUTENTIFIKACIA - spolocna pre vsetky servisy
# =============================================================================
# Tento modul obsahuje API kluc a funkciu na jeho overenie.
# Importuje ho kazdy router, takze zmena autentifikacie na jednom mieste
# sa prejavi v celej aplikacii.
#
# Pouzitie v endpointoch:
#   from app.auth import check_api_key
#   @router.get("/nieco")
#   def nieco(_=Depends(check_api_key)):
#       ...
#
# Klient musi poslat hlavicku:  X-API-Key: <kluc>
# =============================================================================

from fastapi import Header, HTTPException

# API kluc - rovnaky pre vsetkych klientov
API_KEY = "5e5944fad25122ffa096ec690f0c547ebdb282342e822b60ba02fae86d3ef3e2"


def check_api_key(x_api_key: str = Header()):
    """Overi API kluc z HTTP hlavicky X-API-Key.

    FastAPI automaticky prevadza nazov parametra:
      x_api_key (Python) -> X-API-Key (HTTP hlavicka)

    Pouziva sa cez Depends():
      _=Depends(check_api_key) v parametroch endpointu
      - Depends() znamena: "pred zavolanim endpointu najprv zavolaj tuto funkciu"
      - Ak vyhodi HTTPException, endpoint sa nezavola a klient dostane chybu 401
      - _= znamena ze vysledok nepotrebujeme (funkcia nic nevracia, len kontroluje)
    """
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Neplatny API kluc")
