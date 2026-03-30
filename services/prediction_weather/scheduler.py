import time
import threading

from app.services.prediction_weather.database import refresh_all_cities


def start_weather_scheduler():
    """Spusti background vlakno ktore kazdych 30 minut aktualizuje predpovede."""

    def loop():
        time.sleep(5)  # pockaj 5 sekund po starte
        while True:
            print("[WEATHER SCHEDULER] Aktualizujem predpovede...")
            try:
                refresh_all_cities()
            except Exception as e:
                print(f"[WEATHER SCHEDULER] Chyba: {e}")
            time.sleep(30 * 60)  # cakaj 30 minut

    thread = threading.Thread(target=loop)
    thread.daemon = True
    thread.start()
