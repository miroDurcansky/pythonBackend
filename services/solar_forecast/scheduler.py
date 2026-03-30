# =============================================================================
# SCHEDULER - automaticky refresh predikcie vyroby FVE
# =============================================================================
# Bezi v pozadi ako daemon vlakno. Kazdych 60 minut zavola refresh
# pre vsetkych zakaznikov.
#
# DOLEZITE: Scheduler pouziva force=False, takze ak uz pre dnesok
# existuju data, API sa nezavola (setri rate limit forecast.solar).
# Novy fetch prebehne az nasledujuci den.
#
# Volany z main.py pri starte aplikacie:
#   start_solar_scheduler()
# =============================================================================

import time
import threading

from app.services.solar_forecast.database import refresh_all_customers


def start_solar_scheduler():
    """Spusti background vlakno ktore kazdych 60 minut aktualizuje predikciu vyroby FVE."""

    def loop():
        # Kratka pauza po starte - pocka kym sa aplikacia uplne spusti
        time.sleep(10)

        while True:
            print("[SOLAR SCHEDULER] Aktualizujem predikcie vyroby pre vsetkych zakaznikov...")
            try:
                # force=False (default) = preskoci zakaznikov ktori uz maju data pre dnesok
                refresh_all_customers()
            except Exception as e:
                print(f"[SOLAR SCHEDULER] Chyba: {e}")

            # Pockaj 60 minut pred dalsim refreshom
            time.sleep(60 * 60)

    thread = threading.Thread(target=loop)
    thread.daemon = True
    thread.start()
