"""
Veritabanindaki eksik afisleri OMDb API'den cekip tamamlar.
"""

import time

from core_services import OmdbClient, PostgresClient, configure_windows_console


class MissingPosterCompleter:
    def __init__(self) -> None:
        self.db_client = PostgresClient()

    def _get_api_client(self):
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

    def run(self) -> None:
        print("=" * 70)
        print("EKSIK AFISLERI TAMAMLAMA ARACI")
        print("=" * 70)
        print()

        api_client = self._get_api_client()
        if not api_client:
            input("Cikmak icin Enter'a basin...")
            return

        print("\nVeritabani baglantisi kuruluyor...")
        conn = self.db_client.connect()
        if not conn:
            print("HATA: Veritabani baglantisi kurulamadi!")
            input("Cikmak icin Enter'a basin...")
            return

        print("OK: Veritabani baglantisi basarili\n")

        try:
            cursor = conn.cursor()
            print("Eksik afisli filmler araniyor...")
            movies_without_poster = self.db_client.get_movies_without_poster(cursor)

            if not movies_without_poster:
                print("OK: Tum filmlerin afisi mevcut!")
                input("Cikmak icin Enter'a basin...")
                return

            print(f"OK: {len(movies_without_poster)} film eksik afisli bulundu\n")
            print("=" * 70)
            print()

            success_count = 0
            error_count = 0
            not_found_count = 0

            for idx, (movie_id, title, year) in enumerate(movies_without_poster, 1):
                print(
                    f"[{idx}/{len(movies_without_poster)}] {title} ({year if year else 'Yil bilinmiyor'})... ",
                    end="",
                    flush=True,
                )

                result = api_client.fetch_poster(title, year)
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

                try:
                    cursor.execute(
                        """
                        UPDATE movies
                        SET poster_url = %s
                        WHERE id = %s
                        """,
                        (result["poster_url"], movie_id),
                    )
                    conn.commit()
                    print("OK: TAMAMLANDI")
                    success_count += 1
                except Exception as exc:
                    conn.rollback()
                    print(f"HATA: Veritabani guncelleme hatasi - {exc}")
                    error_count += 1

                time.sleep(1)

            print()
            print("=" * 70)
            print("ISLEM TAMAMLANDI")
            print("=" * 70)
            print(f"Basarili: {success_count}")
            print(f"Hata: {error_count}")
            print(f"Bulunamadi: {not_found_count}")
            print(f"Toplam: {len(movies_without_poster)}")
            print("=" * 70)
        except Exception as exc:
            print(f"\nHATA: {exc}")
            conn.rollback()
        finally:
            conn.close()

        input("\nCikmak icin Enter'a basin...")


if __name__ == "__main__":
    configure_windows_console()
    MissingPosterCompleter().run()
