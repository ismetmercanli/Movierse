"""
Icerik tabanli film oneri motoru.

Her film icin agirlikli bir ozellik vektoru olusturur ve tum filmler
arasinda kosinus benzerligi hesaplar.

Ozellikler (agirlik sirasiyla):
    1. Kategoriler (tur)       - 3.0
    2. Oyuncular               - 2.0
    3. Aciklama (TF-IDF)       - 1.5
    4. IMDb puani              - 0.5
    5. is_turkish (TR/yabanci) - 0.4   (cok az: Turk filmleri hafifce birbirine yakin tutar)
    6. Yapim yili              - 0.3

Kullanim:
    from ml import ContentRecommender
    rec = ContentRecommender()
    rec.fit(movies_df)              # DB'den cekilmis DataFrame
    rec.save("ml/models/content_model.joblib")

    rec = ContentRecommender.load("ml/models/content_model.joblib")
    rec.recommend(watched_ids=[1, 5, 23], top_k=10)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import unicodedata

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MultiLabelBinarizer, normalize


# Tiny multilingual stop-word list (TR + EN core).
# Buyuk bir liste degil; TF-IDF zaten yaygin kelimeleri otomatik bastiriyor.
_TURKISH_STOPWORDS = {
    "ve", "ile", "bir", "bu", "da", "de", "ki", "icin", "için", "ama", "fakat",
    "ya", "ne", "mi", "mu", "ise", "ya da", "her", "hep", "cok", "çok", "az",
    "var", "yok", "olan", "olarak", "olur", "oldu", "olmus", "olmuş", "biri",
    "kendi", "kendisi", "bu", "şu", "o", "bunlar", "şunlar", "onlar", "ben",
    "sen", "biz", "siz", "bana", "sana", "ona", "bize", "size", "ona", "onlara",
    "ya", "yani", "gibi", "kadar", "sonra", "once", "önce", "ayni", "aynı",
}

_ENGLISH_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "while", "with", "without",
    "in", "on", "at", "to", "from", "by", "for", "of", "as", "is", "are",
    "was", "were", "be", "been", "being", "this", "that", "these", "those",
    "it", "its", "he", "she", "they", "them", "his", "her", "their", "our",
    "we", "you", "your", "i", "me", "my", "what", "which", "who", "whom",
    "will", "would", "should", "can", "could", "may", "might", "must",
    "have", "has", "had", "do", "does", "did", "not", "no", "yes", "so",
    "than", "then", "there", "here", "out", "up", "down", "into", "over",
    "after", "before", "between", "during", "above", "below", "again", "more",
    "most", "all", "any", "each", "few", "other", "some", "such", "only",
    "own", "same", "too", "very", "just", "now",
}

def _ascii_fold(text: str) -> str:
    """Turkce karakterleri ASCII'ye dusurur (TfidfVectorizer strip_accents=unicode ile uyumlu)."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


# Vectorizer 'strip_accents=unicode' + 'lowercase=True' uyguladigi icin
# stop-word listemizi de ayni donusumden gecirmemiz lazim. Aksi halde
# 'şunlar' -> 'sunlar' donusumu yuzunden uyari aliriz.
STOPWORDS = sorted({_ascii_fold(w.lower()) for w in (_TURKISH_STOPWORDS | _ENGLISH_STOPWORDS)})


@dataclass
class FeatureWeights:
    """Her ozellik bloguna uygulanacak agirliklar.

    Mevcut ayar: 'begenilen filmlere benzer onerilerin one cikmasi' hedefine optimize.
    - Kategori biraz dusurulup (3.0 -> 2.5) like'lara yer acildi
    - Oyuncu yukseltildi (2.0 -> 2.5): begenilen filmler genelde ortak kadro/yonetmen tasir
    - Aciklama yukseltildi (1.5 -> 2.0): begeniler tematik kume olusturur
    """

    category: float = 2.5
    actor: float = 2.5
    description: float = 2.0
    rating: float = 0.5
    is_turkish: float = 0.4   # Turk filmlerini birbirine cok az yakinlastiran ek sinyal
    year: float = 0.3


@dataclass
class TrainStats:
    """Egitim sonrasi diagnostik bilgiler."""

    movie_count: int = 0
    feature_dim: int = 0
    category_dim: int = 0
    actor_dim: int = 0
    description_dim: int = 0
    unique_categories: int = 0
    unique_actors: int = 0
    turkish_movie_count: int = 0
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Yardimci parsing fonksiyonlari (joblib pickle uyumlu olmali => modul seviyesi)
# ---------------------------------------------------------------------------

def _split_csv(value: Optional[str]) -> List[str]:
    """Virgulle ayrilmis bir string'i temiz token listesine cevirir."""
    if not value or pd.isna(value):
        return []
    tokens = [tok.strip() for tok in str(value).split(",")]
    return [t for t in tokens if t and t.upper() != "N/A"]


def _normalize_token(token: str) -> str:
    """Kategori/oyuncu token'larini birlestirme/karsilastirma icin normalize eder."""
    t = token.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


class ContentRecommender:
    """Icerik tabanli film oneri motoru."""

    DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "content_model.joblib")

    def __init__(
        self,
        weights: Optional[FeatureWeights] = None,
        max_description_features: int = 800,
        min_actor_freq: int = 2,
    ) -> None:
        self.weights = weights or FeatureWeights()
        self.max_description_features = max_description_features
        self.min_actor_freq = min_actor_freq

        # Egitimde doldurulacak alanlar
        self.movie_ids: np.ndarray = np.array([], dtype=np.int64)
        self.titles: List[str] = []
        self.id_to_index: Dict[int, int] = {}
        self.feature_matrix: Optional[csr_matrix] = None
        self.similarity_matrix: Optional[np.ndarray] = None

        # Encoder/vectorizer'lari da sakliyoruz (yeni filmleri vektorlestirmek icin gerekecek)
        self.category_encoder: Optional[MultiLabelBinarizer] = None
        self.actor_encoder: Optional[MultiLabelBinarizer] = None
        self.description_vectorizer: Optional[TfidfVectorizer] = None
        self.year_min: float = 0.0
        self.year_max: float = 1.0

        self.stats: TrainStats = TrainStats()

    # ------------------------------------------------------------------
    # Egitim
    # ------------------------------------------------------------------

    def fit(self, movies_df: pd.DataFrame) -> "ContentRecommender":
        """
        movies_df beklenen kolonlar:
            id, title, genre, year, rating, description, actors, country
        """
        required = {"id", "title", "genre", "year", "rating", "description", "actors", "country"}
        missing = required - set(movies_df.columns)
        if missing:
            raise ValueError(f"DataFrame eksik kolonlar: {sorted(missing)}")

        df = movies_df.copy().reset_index(drop=True)
        df["id"] = df["id"].astype(np.int64)

        self.movie_ids = df["id"].to_numpy()
        self.titles = df["title"].astype(str).tolist()
        self.id_to_index = {int(mid): idx for idx, mid in enumerate(self.movie_ids)}

        # 1) KATEGORILER -------------------------------------------------
        category_lists = [
            [_normalize_token(c) for c in _split_csv(g)] for g in df["genre"].fillna("")
        ]
        self.category_encoder = MultiLabelBinarizer(sparse_output=True)
        category_matrix = self.category_encoder.fit_transform(category_lists)

        # 2) OYUNCULAR ---------------------------------------------------
        actor_lists_raw = [
            [_normalize_token(a) for a in _split_csv(a_str)] for a_str in df["actors"].fillna("")
        ]
        # Sadece >= min_actor_freq olan oyunculari tut (gurultuyu azaltir)
        actor_freq: Dict[str, int] = {}
        for actors in actor_lists_raw:
            for a in set(actors):
                actor_freq[a] = actor_freq.get(a, 0) + 1
        kept_actors = {a for a, f in actor_freq.items() if f >= self.min_actor_freq}

        actor_lists = [[a for a in actors if a in kept_actors] for actors in actor_lists_raw]
        self.actor_encoder = MultiLabelBinarizer(sparse_output=True)
        if any(actor_lists):
            actor_matrix = self.actor_encoder.fit_transform(actor_lists)
        else:
            self.actor_encoder.fit([[]])
            actor_matrix = csr_matrix((len(df), 0))

        # 3) ACIKLAMA (TF-IDF) ------------------------------------------
        descriptions = df["description"].fillna("").astype(str).tolist()
        self.description_vectorizer = TfidfVectorizer(
            max_features=self.max_description_features,
            stop_words=STOPWORDS,
            ngram_range=(1, 2),
            min_df=2,
            sublinear_tf=True,
            lowercase=True,
            strip_accents="unicode",
        )
        try:
            description_matrix = self.description_vectorizer.fit_transform(descriptions)
        except ValueError:
            # Cok az film varsa min_df'e takilirsa fallback
            self.description_vectorizer = TfidfVectorizer(
                max_features=self.max_description_features,
                stop_words=STOPWORDS,
                lowercase=True,
                strip_accents="unicode",
            )
            description_matrix = self.description_vectorizer.fit_transform(descriptions)

        # 4) RATING ------------------------------------------------------
        ratings = df["rating"].fillna(0.0).astype(float).to_numpy()
        rating_norm = np.clip(ratings, 0.0, 10.0) / 10.0
        rating_matrix = csr_matrix(rating_norm.reshape(-1, 1))

        # 5) IS_TURKISH (TR vs yabanci) ---------------------------------
        # country alaninda 'Turkey' / 'Türkiye' geciyorsa 1, yoksa 0.
        country_series = df["country"].fillna("").astype(str)
        is_turkish_arr = country_series.apply(self._is_turkish_country).astype(float).to_numpy()
        is_turkish_matrix = csr_matrix(is_turkish_arr.reshape(-1, 1))

        # 6) YIL ---------------------------------------------------------
        years = df["year"].fillna(0).astype(float).to_numpy()
        valid_years = years[years > 0]
        if valid_years.size > 0:
            self.year_min = float(valid_years.min())
            self.year_max = float(valid_years.max())
            if self.year_max == self.year_min:
                self.year_max = self.year_min + 1.0
        else:
            self.year_min, self.year_max = 0.0, 1.0
        year_norm = np.where(
            years > 0,
            (years - self.year_min) / (self.year_max - self.year_min),
            0.0,
        )
        year_matrix = csr_matrix(year_norm.reshape(-1, 1))

        # --- Her blogu L2-normalize edip sonra agirlikla carpiyoruz.
        # Bu sayede agirliklar gercekten katki oraninda etkili olur.
        def _block_norm(m):
            return normalize(m, norm="l2", axis=1, copy=True)

        category_block = _block_norm(category_matrix) * self.weights.category
        actor_block = _block_norm(actor_matrix) * self.weights.actor
        description_block = _block_norm(description_matrix) * self.weights.description
        # Rating/is_turkish/year zaten 1-dim binary/skaler -> direkt agirlik uygula.
        rating_block = rating_matrix * self.weights.rating
        is_turkish_block = is_turkish_matrix * self.weights.is_turkish
        year_block = year_matrix * self.weights.year

        blocks = [
            category_block,
            actor_block,
            description_block,
            rating_block,
            is_turkish_block,
            year_block,
        ]
        feature_matrix = hstack(blocks, format="csr")

        # Son satir-bazli L2-normalize: kosinus benzerligi icin dot-product = cosine olur
        feature_matrix = normalize(feature_matrix, norm="l2", axis=1, copy=False)

        self.feature_matrix = feature_matrix
        self.similarity_matrix = cosine_similarity(feature_matrix, dense_output=True).astype(
            np.float32
        )

        # Diagnostik
        self.stats = TrainStats(
            movie_count=feature_matrix.shape[0],
            feature_dim=feature_matrix.shape[1],
            category_dim=category_matrix.shape[1],
            actor_dim=actor_matrix.shape[1],
            description_dim=description_matrix.shape[1],
            unique_categories=len(self.category_encoder.classes_),
            unique_actors=len(self.actor_encoder.classes_),
            turkish_movie_count=int(is_turkish_arr.sum()),
        )
        if not any(actor_lists):
            self.stats.notes.append("Oyuncu verisi bos -> oyuncu blogu devre disi")
        return self

    @staticmethod
    def _is_turkish_country(country_str: str) -> int:
        """country alanindan Turk filmi olup olmadigini binary olarak dondurur."""
        if not country_str:
            return 0
        lower = country_str.lower()
        # OMDb genelde 'Turkey' dondurur; bazi kayitlarda 'Türkiye' de olabilir.
        return 1 if ("turkey" in lower or "türkiye" in lower or "turkiye" in lower) else 0

    # ------------------------------------------------------------------
    # Oneri / Sorgulama
    # ------------------------------------------------------------------

    def recommend(
        self,
        watched_ids: Sequence[int],
        top_k: int = 10,
        exclude_watched: bool = True,
        min_score: float = 0.0,
        liked_ids: Optional[Sequence[int]] = None,
        disliked_ids: Optional[Sequence[int]] = None,
        dislike_weight: float = 1.0,
        like_boost: float = 3.0,
    ) -> List[Dict[str, float]]:
        """
        Kullanicinin izledigi/begendigi filmlere benzer top_k filmi dondurur.

        Pozitif sinyal:
            watched_ids agirligi  = 1
            liked_ids   agirligi  = like_boost  (varsayilan 3.0)
            -> Begenilen filmler izlenenlerden 'like_boost' kati guclu sinyal verir.

        Negatif sinyal:
            disliked_ids  -> ortalama benzerligi `dislike_weight` ile cezalandirir.

        Skor = pozitif_benzerlik_agirlikli_ortalama - dislike_weight * ortalama_negatif

        Donus: [{"movie_id": int, "title": str, "score": float}, ...]
        """
        if self.similarity_matrix is None or self.feature_matrix is None:
            raise RuntimeError("Model henuz egitilmemis. Once fit() veya load() cagirin.")

        liked_ids = list(liked_ids or [])
        disliked_ids = list(disliked_ids or [])
        watched_ids_list = list(watched_ids or [])

        liked_set = {int(m) for m in liked_ids if int(m) in self.id_to_index}
        watched_set = {int(m) for m in watched_ids_list if int(m) in self.id_to_index}
        # Bir film hem watched hem liked olabilir -> liked tarafini sayariz (boost alir)
        watched_only_set = watched_set - liked_set

        liked_indices = [self.id_to_index[mid] for mid in liked_set]
        watched_only_indices = [self.id_to_index[mid] for mid in watched_only_set]
        negative_indices = [
            self.id_to_index[int(mid)] for mid in disliked_ids if int(mid) in self.id_to_index
        ]

        # Hicbir sinyal yoksa -> oneri yok
        if not liked_indices and not watched_only_indices and not negative_indices:
            return []

        sim_matrix = self.similarity_matrix
        like_boost = float(max(0.0, like_boost))

        # Pozitif vektor: begenilen ve izlenenleri agirlikli ortalama
        if liked_indices or watched_only_indices:
            weighted_sum = np.zeros(sim_matrix.shape[0], dtype=sim_matrix.dtype)
            total_weight = 0.0
            if watched_only_indices:
                weighted_sum = weighted_sum + sim_matrix[watched_only_indices].sum(axis=0)
                total_weight += float(len(watched_only_indices))
            if liked_indices:
                weighted_sum = weighted_sum + like_boost * sim_matrix[liked_indices].sum(axis=0)
                total_weight += like_boost * float(len(liked_indices))

            if total_weight > 0:
                pos_vec = weighted_sum / total_weight
            else:
                pos_vec = np.zeros(sim_matrix.shape[0], dtype=sim_matrix.dtype)
        else:
            pos_vec = np.zeros(sim_matrix.shape[0], dtype=sim_matrix.dtype)

        if negative_indices:
            neg_vec = sim_matrix[negative_indices].mean(axis=0)
            sim_vec = pos_vec - float(dislike_weight) * neg_vec
        else:
            sim_vec = pos_vec.copy()

        # Hem izlenen hem begenilen hem begenilmeyen filmleri sonuctan cikar
        exclusion_indices = set()
        if exclude_watched:
            exclusion_indices.update(watched_only_indices)
            exclusion_indices.update(liked_indices)
        # Begenilmeyenleri her zaman ele - bir daha onerme
        exclusion_indices.update(negative_indices)

        if exclusion_indices:
            sim_vec = sim_vec.copy()
            for idx in exclusion_indices:
                sim_vec[idx] = -np.inf

        # En yuksek top_k indeksini bul
        if top_k >= sim_vec.size:
            order = np.argsort(-sim_vec)
        else:
            partial = np.argpartition(-sim_vec, top_k)[:top_k]
            order = partial[np.argsort(-sim_vec[partial])]

        results: List[Dict[str, float]] = []
        for idx in order:
            score = float(sim_vec[idx])
            if not np.isfinite(score) or score < min_score:
                continue
            results.append(
                {
                    "movie_id": int(self.movie_ids[idx]),
                    "title": self.titles[idx],
                    "score": round(score, 4),
                }
            )
            if len(results) >= top_k:
                break
        return results

    def similar_to_movie(self, movie_id: int, top_k: int = 5) -> List[Dict[str, float]]:
        """Tek bir filme en benzer top_k filmi dondurur (sanity check icin)."""
        return self.recommend([movie_id], top_k=top_k, exclude_watched=True)

    # ------------------------------------------------------------------
    # Kaydetme / Yukleme
    # ------------------------------------------------------------------

    def save(self, path: Optional[str] = None) -> str:
        path = path or self.DEFAULT_MODEL_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump(self, path, compress=3)
        return path

    @classmethod
    def load(cls, path: Optional[str] = None) -> "ContentRecommender":
        path = path or cls.DEFAULT_MODEL_PATH
        return joblib.load(path)
