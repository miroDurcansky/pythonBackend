import time
import threading

from app.services.solar_forecast.database import refresh_all_customers


def start_solar_scheduler():
    """Spusti background vlakno ktore kazdych 60 minut aktualizuje predikciu vyroby FVE."""

    def loop():
        time.sleep(10)  # pockaj 10 sekund po starte
        while True:
            print("[SOLAR SCHEDULER] Aktualizujem predikcie vyroby pre vsetkych zakaznikov...")
            try:
                refresh_all_customers()
            except Exception as e:
                print(f"[SOLAR SCHEDULER] Chyba: {e}")
            time.sleep(60 * 60)  # cakaj 60 minut

    thread = threading.Thread(target=loop)
    thread.daemon = True
    thread.start()
