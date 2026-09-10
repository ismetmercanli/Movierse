"""
Veritabanindaki filmlerin eksik 'actors' bilgisini OMDb API'den cekip doldurur.

- Sadece actors alani NULL veya bos olan filmler icin istek atar.
- OMDb gunluk 1000 istek limitine takilmamak icin istekler arasi 1 sn bekler.
- Calistirildikca yeniden calistirilabilir (idempotent).
"""

import os
import time

from core_services import OmdbClient, PostgresClient, configure_windows_console


NON_INTERACTIVE = bool(os.getenv("OMDB_API_KEY", "").strip())


def _wait_exit(message: str = "Cikmak icin Enter'a basin...") -> None:
    if NON_INTERACTIVE:
        return
    input(message)


class ActorsBackfiller:
    def __init__(self) -> None:
        self.db_client = PostgresClient()

    def _get_api_client(self):
        env_key = os.getenv("OMDB_API_KEY", "").strip()
        if env_key:
            api_key = env_key
            print("OMDB_API_KEY environment variable'dan API key alindi.")
        else:
            api_key = input("OMDb API Key'inizi girin: ").strip()
        if not api_key:
            print("HATA: API Key gerekli!")
            return None

        print("\nAPI Key test ediliyor...")
        api_client = OmdbClient(api_key)
        is_valid, message = api_client.test_api_key()
        if not is_valid:
            print(f"HATA: {message}")
            return None

        print(f"OK: {message}")
        return api_client

    @staticmethod
    def _get_movies_without_actors(cursor):
        cursor.execute(
            """
            SELECT id, title, year
            FROM movies
            WHERE actors IS NULL OR TRIM(actors) = '' OR UPPER(actors) = 'N/A'
            ORDER BY id
            """
        )
        return cursor.fetchall()

    def run(self) -> None:
        print("=" * 70)
        print("FILM OYUNCULARINI TAMAMLAMA ARACI (OMDb)")
        print("=" * 70)
        print()

        print("Veritabani baglantisi kuruluyor...")
        conn = self.db_client.connect()
        if not conn:
            print("HATA: Veritabani baglantisi kurulamadi!")
            _wait_exit()
            return

        print("OK: Veritabani baglantisi basarili\n")

        try:
            cursor = conn.cursor()

            # Geriye uyumluluk: actors kolonu yoksa olustur
            self.db_client.ensure_actors_column(cursor)
            conn.commit()

            print("Oyuncu bilgisi eksik filmler araniyor...")
            movies = self._get_movies_without_actors(cursor)

            if not movies:
                print("OK: Tum filmlerde oyuncu bilgisi mevcut!")
                _wait_exit()
                return

            print(f"OK: {len(movies)} film icin oyuncu cekilecek\n")
            print("-" * 70)
            print("OMDb API Key gerekli (https://www.omdbapi.com/apikey.aspx)")
            print("-" * 70)

            api_client = self._get_api_client()
            if not api_client:
                _wait_exit()
                return

            print()
            print("=" * 70)
            print()

            success_count = 0
            error_count = 0
            not_found_count = 0

            for idx, (movie_id, title, year) in enumerate(movies, 1):
                year_str = str(year) if year else "?"
                print(
                    f"[{idx}/{len(movies)}] {title} ({year_str})... ",
                    end="",
                    flush=True,
                )

                result = api_client.fetch_movie(title)
                if "error" in result:
                    error_msg = result["error"]
                    print(f"BASARISIZ ({error_msg})")

                    if "API Key" in error_msg:
                        print("\nHATA: API Key sorunu tespit edildi. Islem durduruluyor.")
                        break
                    if "bulunamadi" in error_msg.lower() or "not found" in error_msg.lower():
                        not_found_count += 1
                    else:
                        error_count += 1

                    time.sleep(1)
                    continue

                actors = result.get("actors", "")
                if not actors:
                    print("BOS (OMDb oyuncu dondurmedi)")
                    not_found_count += 1
                    time.sleep(1)
                    continue

                try:
                    cursor.execute(
                        """
                        UPDATE movies
                        SET actors = %s
                        WHERE id = %s
                        """,
                        (actors, movie_id),
                    )
                    conn.commit()
                    short = actors if len(actors) <= 60 else actors[:57] + "..."
                    print(f"OK -> {short}")
                    success_count += 1
                except Exception as exc:
                    conn.rollback()
                    print(f"HATA: DB guncellenemedi - {exc}")
                    error_count += 1

                time.sleep(1)

            print()
            print("=" * 70)
            print("ISLEM TAMAMLANDI")
            print("=" * 70)
            print(f"Basarili: {success_count}")
            print(f"Hata: {error_count}")
            print(f"Bulunamadi / Bos: {not_found_count}")
            print(f"Toplam islenen: {len(movies)}")
            print("=" * 70)
        except Exception as exc:
            print(f"\nBEKLENMEYEN HATA: {exc}")
            conn.rollback()
        finally:
            conn.close()

        _wait_exit()


if __name__ == "__main__":
    configure_windows_console()
    ActorsBackfiller().run()
