"""
Bilinen dusuk/orta puanli filmleri OMDb API'den cekip veritabanina ekler.

Amac: oneri modelinin egitim verisini cesitlendirmek - sadece yuksek puanli
filmleri tanidiginda, dusuk puanli filmleri ayirt etmeyi de ogrenebilsin.

Tum filmler 'actors' bilgisiyle birlikte cekilir (oyuncu sinyali icin).

Calistirma:
    python dusuk_rating_filmleri_ekle.py
    veya OMDB_API_KEY env var ile:
    $env:OMDB_API_KEY="xxx"; python dusuk_rating_filmleri_ekle.py
"""

import os
import time

from core_services import OmdbClient, PostgresClient, configure_windows_console


# (Baslik, IMDb ID) ciftleri.
# IMDb ID kullanmak title cakismalarini engelliyor (orn. "Cats" - 2019 musical vs documentary).
# Karisik bir mix: gercekten cok kotu (1-3), orta-zayif (3-5), tartismali (5-6).
LOW_RATED_MOVIES = [
    # Klasik "en kotu film" adaylari
    ("Plan 9 from Outer Space", "tt0052077"),       # 1959, ~4.0
    ("Manos: The Hands of Fate", "tt0060666"),      # 1966, ~1.9
    ("The Room", "tt0368226"),                       # 2003, ~3.7
    ("Birdemic: Shock and Terror", "tt1316037"),     # 2010, ~1.8
    ("Battlefield Earth", "tt0185183"),              # 2000, ~2.5
    ("Disaster Movie", "tt1213644"),                 # 2008, ~1.9
    ("Epic Movie", "tt0799949"),                     # 2007, ~2.4
    ("Date Movie", "tt0450385"),                     # 2006, ~2.9
    ("Meet the Spartans", "tt1073498"),              # 2008, ~2.7
    ("Vampires Suck", "tt1666186"),                  # 2010, ~3.4
    ("From Justin to Kelly", "tt0341886"),           # 2003, ~1.9
    ("Glitter", "tt0240515"),                        # 2001, ~2.5
    ("Crossroads", "tt0285492"),                     # 2002, ~3.5
    ("Son of the Mask", "tt0362227"),                # 2005, ~2.3
    ("Baby Geniuses", "tt0120602"),                  # 1999, ~2.4
    ("Howard the Duck", "tt0091225"),                # 1986, ~4.7

    # Aksiyon / Macera basarisizliklari
    ("The Last Airbender", "tt0938283"),             # 2010, ~4.0
    ("Catwoman", "tt0327554"),                       # 2004, ~3.4
    ("Steel", "tt0120053"),                          # 1997, ~2.7
    ("Eragon", "tt0449010"),                         # 2006, ~5.0
    ("Dragonball Evolution", "tt1098327"),           # 2009, ~2.6
    ("The Wicker Man", "tt0450345"),                 # 2006, ~3.7
    ("Anaconda", "tt0118615"),                       # 1997, ~4.9
    ("Super Mario Bros.", "tt0108255"),              # 1993, ~4.2
    ("Mac and Me", "tt0095809"),                     # 1988, ~3.3
    ("Jaws: The Revenge", "tt0093090"),              # 1987, ~3.0

    # Adam Sandler tarzi gisede tutmus ama dusuk puanli komediler
    ("Jack and Jill", "tt0810913"),                  # 2011, ~3.4
    ("Norbit", "tt0477051"),                         # 2007, ~4.2
    ("White Chicks", "tt0365907"),                   # 2004, ~5.7
    ("The Cat in the Hat", "tt0312109"),             # 2003, ~3.9

    # Daha yeni / animasyon basarisizliklari
    ("The Emoji Movie", "tt4877122"),                # 2017, ~3.4
    ("Cats", "tt5697572"),                           # 2019, ~2.8
    ("Pixels", "tt2120120"),                         # 2015, ~5.6
    ("Movie 43", "tt1333125"),                       # 2013, ~4.3
    ("Suicide Squad", "tt1386697"),                  # 2016, ~5.9
    ("Fant4stic", "tt1502712"),                      # 2015, Fantastic Four ~4.3
    ("Justice League", "tt0974015"),                 # 2017, ~6.1 (tartismali)
    ("Twilight", "tt1099212"),                       # 2008, ~5.3
    ("Fifty Shades of Grey", "tt2322441"),           # 2015, ~4.1

    # Korku / B-tipi
    ("Showgirls", "tt0114436"),                      # 1995, ~5.0
    ("Sharknado", "tt2724064"),                      # 2013, ~3.3
    ("The Happening", "tt0949731"),                  # 2008, ~5.0
    ("Lady in the Water", "tt0452637"),              # 2006, ~5.5
    ("Ballistic: Ecks vs. Sever", "tt0270846"),      # 2002, ~3.1
    ("Gigli", "tt0299930"),                          # 2003, ~2.6

    # Sequel basarisizliklari
    ("Speed 2: Cruise Control", "tt0120179"),        # 1997, ~3.8
    ("Grease 2", "tt0084021"),                       # 1982, ~4.6
    ("Garfield: A Tail of Two Kitties", "tt0431308"),# 2006, ~4.0
    ("Alvin and the Chipmunks: The Squeakquel", "tt1232200"),  # 2009, ~4.5

    # Genis aralikta orta-zayif filmler (egitim cesitliligi icin)
    ("Spice World", "tt0119942"),                    # 1997, ~3.5
    ("Garbage Pail Kids Movie", "tt0091112"),        # 1987, ~3.0
    ("Battlefield: Los Angeles", "tt1217613"),       # 2011, ~5.7 -> Battle: Los Angeles
    ("Dungeons & Dragons", "tt0190374"),             # 2000, ~3.6
    ("Trog", "tt0066588"),                           # 1970, ~3.5
    ("The Spirit", "tt0831887"),                     # 2008, ~4.7
    ("Doogal", "tt0455653"),                         # 2006, ~3.6
    ("Highlander II: The Quickening", "tt0102034"),  # 1991, ~3.6
    ("Batman & Robin", "tt0118688"),                 # 1997, ~3.8
    ("Wild Wild West", "tt0120891"),                 # 1999, ~4.9
]


class LowRatedMoviesImporter:
    """populer_filmler_ekle.py ile ayni desende fakat dusuk puanli filmler icin."""

    def __init__(self) -> None:
        self.db_client = PostgresClient()

    def _create_api_client(self):
        env_key = os.getenv("OMDB_API_KEY", "").strip()
        if env_key:
            api_key = env_key
            print("OMDB_API_KEY environment variable'dan API key alindi.")
        else:
            api_key = input("OMDb API Key girin: ").strip()
        if not api_key:
            print("HATA: API Key bos olamaz!")
            return None

        print("\nAPI Key test ediliyor...")
        api_client = OmdbClient(api_key)
        is_valid, message = api_client.test_api_key()
        print(f"Sonuc: {message}")
        if not is_valid:
            print("\nHATA: API Key gecersiz!")
            return None

        print("API Key gecerli!\n")
        return api_client

    def run(self) -> None:
        print("=" * 70)
        print("DUSUK / ORTA PUANLI FILMLERI VERITABANINA EKLEME")
        print("=" * 70)
        print()
        print(f"Toplam {len(LOW_RATED_MOVIES)} film denenecek.")
        print("OMDb'de bulunamayanlar atlanir. Veritabaninda olanlar atlanir.")
        print()

        api_client = self._create_api_client()
        if api_client is None:
            return

        print("Veritabani baglantisi kuruluyor...")
        conn = self.db_client.connect()
        if not conn:
            print("HATA: Veritabani baglantisi kurulamadi!")
            return
        print("Veritabani baglantisi basarili!\n")

        # actors kolonunun var oldugunu garanti et (geriye uyumluluk)
        cursor = conn.cursor()
        try:
            self.db_client.ensure_actors_column(cursor)
            conn.commit()
        except Exception as exc:
            print(f"UYARI: actors kolonu kontrol edilemedi: {exc}")
            conn.rollback()

        print("=" * 70)
        print()

        added_count = 0
        skipped_existing = 0
        not_found_count = 0
        error_count = 0
        rating_total = 0.0
        rating_n = 0

        for i, (movie_title, imdb_id) in enumerate(LOW_RATED_MOVIES, 1):
            label = f"[{i:>2}/{len(LOW_RATED_MOVIES)}] {movie_title}"
            print(f"{label:<70}", end=" ", flush=True)

            movie_data = api_client.fetch_movie(movie_title, imdb_id)

            if "error" in movie_data:
                error_msg = movie_data["error"]
                print(f"BULUNAMADI ({error_msg})")
                if "API Key" in error_msg:
                    print("\nKRITIK: API Key sorunu. Islem durduruluyor.")
                    break
                not_found_count += 1
                time.sleep(1)
                continue

            try:
                if self.db_client.movie_exists(cursor, movie_data.get("title", "")):
                    print("ZATEN MEVCUT (atlandi)")
                    skipped_existing += 1
                else:
                    self.db_client.add_movie(cursor, movie_data)
                    conn.commit()
                    rating = movie_data.get("rating")
                    if rating is not None:
                        rating_total += rating
                        rating_n += 1
                    rating_str = f"{rating}" if rating is not None else "?"
                    print(f"EKLENDI  (IMDb: {rating_str})")
                    added_count += 1
            except Exception as exc:
                conn.rollback()
                print(f"HATA: {exc}")
                error_count += 1

            time.sleep(1)

        conn.close()

        avg_rating = (rating_total / rating_n) if rating_n else 0.0
        print()
        print("=" * 70)
        print("ISLEM TAMAMLANDI!")
        print("=" * 70)
        print(f"Eklenen          : {added_count}")
        print(f"Atlanan (mevcut) : {skipped_existing}")
        print(f"Bulunamadi       : {not_found_count}")
        print(f"Hata             : {error_count}")
        print(f"Toplam denenen   : {len(LOW_RATED_MOVIES)}")
        if rating_n:
            print(f"Eklenenlerin ortalama IMDb puani: {avg_rating:.2f} ({rating_n} film)")
        print("=" * 70)
        print()
        print("NOT: Yeni filmleri modele dahil etmek icin:")
        print("     python -m ml.train")


if __name__ == "__main__":
    configure_windows_console()
    LowRatedMoviesImporter().run()
