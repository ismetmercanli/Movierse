"""
Veritabanindaki filmlerin eksik 'country' bilgisini OMDb API'den cekip doldurur.

- Sadece country alani NULL veya bos olan filmler icin istek atar.
- Idempotent: yeniden calistirilabilir.
- OMDB_API_KEY env var verilirse non-interactive calisir.
"""

import os
import time

from core_services import OmdbClient, PostgresClient, configure_windows_console


NON_INTERACTIVE = bool(os.getenv("OMDB_API_KEY", "").strip())


def _wait_exit(message: str = "Cikmak icin Enter'a basin...") -> None:
    if NON_INTERACTIVE:
        return
    input(message)


class CountryBackfiller:
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
    def _get_movies_without_country(cursor):
        cursor.execute(
            """
            SELECT id, title, year
            FROM movies
            WHERE country IS NULL OR TRIM(country) = '' OR UPPER(country) = 'N/A'
            ORDER BY id
            """
        )
        return cursor.fetchall()

    def run(self) -> None:
        print("=" * 70)
        print("FILM ULKELERINI TAMAMLAMA ARACI (OMDb)")
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

            # Geriye uyumluluk: country kolonu yoksa olustur
            self.db_client.ensure_country_column(cursor)
            conn.commit()

            print("Ulke bilgisi eksik filmler araniyor...")
            movies = self._get_movies_without_country(cursor)

            if not movies:
                print("OK: Tum filmlerde ulke bilgisi mevcut!")
                _wait_exit()
                return

            print(f"OK: {len(movies)} film icin ulke cekilecek\n")
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
            turkish_count = 0

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
                        print("\nHATA: API Key sorunu. Durduruluyor.")
                        break
                    if "bulunamadi" in error_msg.lower() or "not found" in error_msg.lower():
                        not_found_count += 1
                    else:
                        error_count += 1

                    time.sleep(1)
                    continue

                country = result.get("country", "")
                if not country:
                    print("BOS (OMDb ulke dondurmedi)")
                    not_found_count += 1
                    time.sleep(1)
                    continue

                try:
                    cursor.execute(
                        """
                        UPDATE movies
                        SET country = %s
                        WHERE id = %s
                        """,
                        (country, movie_id),
                    )
                    conn.commit()
                    is_tr = "Turkey" in country
                    if is_tr:
                        turkish_count += 1
                    flag = " [TR]" if is_tr else ""
                    short = country if len(country) <= 50 else country[:47] + "..."
                    print(f"OK -> {short}{flag}")
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
            print(f"Tespit edilen Turk filmi: {turkish_count}")
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
    CountryBackfiller().run()
