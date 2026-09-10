"""
Icerik tabanli oneri modelini DB'deki filmlerden egitir ve diske kaydeder.

Calistirma:
    python -m ml.train
veya
    python ml/train.py
"""

from __future__ import annotations

import os
import sys
from typing import Optional

import pandas as pd

# Modul yapilandirmasi: 'python ml/train.py' ile dogrudan calistirildiginda
# 'ml' paketinin gorulebilmesi icin proje koklerini sys.path'e ekle.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core_services import PostgresClient, configure_windows_console  # noqa: E402
from ml.content_recommender import ContentRecommender, FeatureWeights  # noqa: E402


SANITY_CHECK_TITLES = [
    "Iron Man",
    "The Dark Knight",
    "Toy Story",
    "Fight Club",
    "Çakallarla Dans",
    "Inception",
]


def load_movies_dataframe(db_client: Optional[PostgresClient] = None) -> pd.DataFrame:
    """movies tablosunu DataFrame olarak yukler."""
    db_client = db_client or PostgresClient()
    conn = db_client.connect()
    if conn is None:
        raise RuntimeError("Veritabani baglantisi kurulamadi")

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, genre, year, rating, description,
                   COALESCE(actors, '') AS actors,
                   COALESCE(country, '') AS country
            FROM movies
            ORDER BY id
            """
        )
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        df = pd.DataFrame(rows, columns=columns)
    finally:
        conn.close()

    return df


def train_and_save(
    weights: Optional[FeatureWeights] = None,
    output_path: Optional[str] = None,
    verbose: bool = True,
) -> ContentRecommender:
    if verbose:
        print("=" * 70)
        print("CONTENT-BASED ONERI MODELI EGITIMI")
        print("=" * 70)

    if verbose:
        print("\n[1/4] Veritabanindan filmler cekiliyor...")
    movies_df = load_movies_dataframe()
    if verbose:
        print(f"  -> {len(movies_df)} film yuklendi")
        print(f"  -> Oyuncu bilgisi olan film: {(movies_df['actors'].str.len() > 0).sum()}")
        print(f"  -> Aciklama dolu film     : {(movies_df['description'].fillna('').str.len() > 0).sum()}")

    if movies_df.empty:
        raise RuntimeError("Veritabaninda hic film yok. Once veri ekleyin.")

    if verbose:
        print("\n[2/4] Ozellik vektorleri olusturuluyor ve model fit ediliyor...")

    recommender = ContentRecommender(weights=weights)
    recommender.fit(movies_df)

    stats = recommender.stats
    if verbose:
        print(f"  -> Toplam film          : {stats.movie_count}")
        print(f"  -> Toplam ozellik boyutu: {stats.feature_dim}")
        print(f"     * Kategori dim       : {stats.category_dim}  ({stats.unique_categories} benzersiz)")
        print(f"     * Oyuncu dim         : {stats.actor_dim}  ({stats.unique_actors} benzersiz, min_freq={recommender.min_actor_freq})")
        print(f"     * Aciklama TF-IDF dim: {stats.description_dim}")
        print(f"     * Rating dim         : 1")
        print(f"     * is_turkish dim     : 1   ({stats.turkish_movie_count} Turk filmi)")
        print(f"     * Yil dim            : 1   (min={recommender.year_min:.0f}, max={recommender.year_max:.0f})")
        if stats.notes:
            for note in stats.notes:
                print(f"  ! Not: {note}")

    if verbose:
        print("\n[3/4] Sanity check: bilinen filmlere top-5 benzer film")
        title_to_id = {t.lower(): int(mid) for t, mid in zip(recommender.titles, recommender.movie_ids)}
        for title in SANITY_CHECK_TITLES:
            mid = title_to_id.get(title.lower())
            if mid is None:
                print(f"  - '{title}': DB'de yok, atlandi")
                continue
            similar = recommender.similar_to_movie(mid, top_k=5)
            print(f"\n  '{title}' filmine en benzer:")
            for s in similar:
                print(f"     {s['score']:.3f}  {s['title']}")

    if verbose:
        print("\n[4/4] Model diske kaydediliyor...")
    saved_path = recommender.save(output_path)
    if verbose:
        size_kb = os.path.getsize(saved_path) / 1024.0
        print(f"  -> {saved_path}  ({size_kb:.1f} KB)")
        print("\nEGITIM TAMAMLANDI.")
        print("=" * 70)

    return recommender


def main() -> int:
    configure_windows_console()
    try:
        train_and_save(verbose=True)
        return 0
    except Exception as exc:  # pragma: no cover
        print(f"\nHATA: Egitim sirasinda hata olustu: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
