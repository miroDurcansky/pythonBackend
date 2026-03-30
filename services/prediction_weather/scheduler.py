# =============================================================================
# SCHEDULER - automaticky refresh predpovedi pocasia
# =============================================================================
# Bezi v pozadi ako daemon vlakno (daemon = automaticky sa zastavi ked
# skonci hlavny program). Kazdych 30 minut stiahne nove predpovede
# pre vsetky mesta v databaze.
#
# Volany z main.py pri starte aplikacie:
#   start_weather_scheduler()
# =============================================================================

import time
import threading

from app.services.prediction_weather.database import refresh_all_cities


def start_weather_scheduler():
    """Spusti background vlakno ktore kazdych 30 minut aktualizuje predpovede."""

    def loop():
        # Kratky pauza po starte - pocka kym sa aplikacia uplne spusti
        time.sleep(5)

        while True:
            print("[WEATHER SCHEDULER] Aktualizujem predpovede...")
            try:
                refresh_all_cities()
            except Exception as e:
                # Chybu zachytime aby scheduler nespadol a pokracoval dalej
                print(f"[WEATHER SCHEDULER] Chyba: {e}")

            # Pockaj 30 minut pred dalsim refreshom
            time.sleep(30 * 60)

    # Vytvor a spusti vlakno
    # daemon=True znamena ze vlakno sa automaticky zastavi pri ukonceni programu
    thread = threading.Thread(target=loop)
    thread.daemon = True
    thread.start()
