"""
Populer filmleri OMDb API'den cekip veritabanina ekler.
"""

import time

from core_services import OmdbClient, PostgresClient, configure_windows_console


POPULAR_MOVIES = [
    ("The Shawshank Redemption", "tt0111161"),
    ("The Godfather", "tt0068646"),
    ("The Dark Knight", "tt0468569"),
    ("Pulp Fiction", "tt0110912"),
    ("The Lord of the Rings: The Return of the King", "tt0167260"),
    ("Forrest Gump", "tt0109830"),
    ("Inception", "tt1375666"),
    ("The Matrix", "tt0133093"),
    ("Goodfellas", "tt0099685"),
    ("Star Wars", "tt0076759"),
    ("The Lord of the Rings: The Fellowship of the Ring", "tt0120737"),
    ("Fight Club", "tt0137523"),
    ("The Lord of the Rings: The Two Towers", "tt0167261"),
    ("Interstellar", "tt0816692"),
    ("The Godfather Part II", "tt0071562"),
    ("The Silence of the Lambs", "tt0102926"),
    ("Saving Private Ryan", "tt0120815"),
    ("Schindler's List", "tt0108052"),
    ("Se7en", "tt0114369"),
    ("The Green Mile", "tt0120689"),
    ("The Usual Suspects", "tt0114814"),
    ("Leon", "tt0110413"),
    ("The Prestige", "tt0482571"),
    ("Gladiator", "tt0172495"),
    ("The Departed", "tt0407887"),
    ("The Lion King", "tt0110357"),
    ("Terminator 2: Judgment Day", "tt0103064"),
    ("Back to the Future", "tt0088763"),
    ("The Avengers", "tt0848228"),
    ("Titanic", "tt0120338"),
    ("Avatar", "tt0499549"),
    ("Jurassic Park", "tt0107290"),
    ("The Dark Knight Rises", "tt1345836"),
    ("Iron Man", "tt0371746"),
    ("Spider-Man: Into the Spider-Verse", "tt4633694"),
    ("Toy Story", "tt0114709"),
    ("Finding Nemo", "tt0266543"),
    ("The Incredibles", "tt0317705"),
    ("Up", "tt1049413"),
    ("WALL-E", "tt0910970"),
    ("The Shining", "tt0081505"),
    ("Alien", "tt0078748"),
    ("Aliens", "tt0090605"),
    ("Blade Runner", "tt0083658"),
    ("2001: A Space Odyssey", "tt0062622"),
    ("Apocalypse Now", "tt0078788"),
    ("Casino Royale", "tt0381061"),
    ("Skyfall", "tt1074638"),
    ("Mad Max: Fury Road", "tt1392190"),
    ("Django Unchained", "tt1853728"),
    ("Inglourious Basterds", "tt0361748"),
]


class PopularMoviesImporter:
    def __init__(self) -> None:
        self.db_client = PostgresClient()

    def _create_api_client(self):
        api_key = input("OMDb API Key girin: ").strip()
        if not api_key:
            print("HATA: API Key bos olamaz!")
            return None

        print("\nAPI Key test ediliyor...")
        api_client = OmdbClient(api_key)
        is_valid, message = api_client.test_api_key()
        print(f"Sonuc: {message}")
        if not is_valid:
            print("\nHATA: API Key gecersiz! Lutfen dogru API key girin.")
            print("API Key almak icin: https://www.omdbapi.com/apikey.aspx")
            return None

        print("API Key gecerli!\n")
        return api_client

    def run(self) -> None:
        print("=" * 70)
        print("POPULER FILMLERI OMDb API'DEN CEKIP VERITABANINA EKLEME")
        print("=" * 70)
        print()

        api_client = self._create_api_client()
        if not api_client:
            input("\nDevam etmek icin Enter'a basin...")
            return

        print("Veritabani baglantisi kuruluyor...")
        conn = self.db_client.connect()
        if not conn:
            print("HATA: Veritabani baglantisi kurulamadi!")
            input("\nDevam etmek icin Enter'a basin...")
            return

        print("Veritabani baglantisi basarili!\n")
        print("=" * 70)
        print(f"Toplam {len(POPULAR_MOVIES)} film islenecek...")
        print("=" * 70)
        print()

        cursor = conn.cursor()
        added_count = 0
        skipped_count = 0
        error_count = 0

        for i, (movie_title, imdb_id) in enumerate(POPULAR_MOVIES, 1):
            print(f"[{i}/{len(POPULAR_MOVIES)}] {movie_title}...", end=" ")
            movie_data = api_client.fetch_movie(movie_title, imdb_id)

            if "error" in movie_data:
                error_msg = movie_data["error"]
                print(f"BULUNAMADI ({error_msg})")

                if "API Key" in error_msg or "401" in error_msg or "Invalid" in error_msg:
                    print("\n" + "=" * 70)
                    print("KRITIK HATA: API Key gecersiz!")
                    print("=" * 70)
                    print("Lutfen dogru API key ile tekrar deneyin.")
                    conn.close()
                    input("\nDevam etmek icin Enter'a basin...")
                    return

                error_count += 1
                time.sleep(1)
                continue

            if self.db_client.movie_exists(cursor, movie_data.get("title", "")):
                print("ZATEN MEVCUT (atlandi)")
                skipped_count += 1
            else:
                try:
                    self.db_client.add_movie(cursor, movie_data)
                    conn.commit()
                    print(f"EKLENDI [OK] (IMDb: {movie_data.get('rating', 'N/A')})")
                    added_count += 1
                except Exception as exc:
                    conn.rollback()
                    print(f"HATA: {exc}")
                    error_count += 1

            time.sleep(1)

        conn.close()
        print()
        print("=" * 70)
        print("ISLEM TAMAMLANDI!")
        print("=" * 70)
        print(f"Eklenen: {added_count}")
        print(f"Atlanan (zaten mevcut): {skipped_count}")
        print(f"Hata: {error_count}")
        print(f"Toplam: {len(POPULAR_MOVIES)}")
        print("=" * 70)
        print()
        input("Devam etmek icin Enter'a basin...")


if __name__ == "__main__":
    configure_windows_console()
    PopularMoviesImporter().run()
