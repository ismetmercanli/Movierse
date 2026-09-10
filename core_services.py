"""Ortak veritabani ve OMDb servisleri."""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional, Tuple

import psycopg2
import requests


def configure_windows_console() -> None:
    """Windows'ta UTF-8 ciktiyi zorlar."""
    if sys.platform != "win32":
        return

    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


class DBConfig:
    """Veritabani ayarlarini environment'dan toplar."""

    @staticmethod
    def from_env() -> Dict[str, str]:
        return {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": os.getenv("DB_PORT", "5432"),
            "database": os.getenv("DB_NAME", "movies_db"),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "1234"),
        }


class PostgresClient:
    """Basit PostgreSQL yardimci sinifi."""

    def __init__(self, config: Optional[Dict[str, str]] = None) -> None:
        self.config = config or DBConfig.from_env()

    def connect(self):
        try:
            return psycopg2.connect(**self.config)
        except Exception as exc:
            print(f"Veritabani baglanti hatasi: {exc}")
            return None

    @staticmethod
    def movie_exists(cursor, title: str) -> bool:
        cursor.execute("SELECT id FROM movies WHERE LOWER(title) = LOWER(%s)", (title,))
        return cursor.fetchone() is not None

    @staticmethod
    def add_movie(cursor, movie_data: Dict[str, Any]) -> None:
        cursor.execute(
            """
            INSERT INTO movies (title, genre, year, rating, description, poster_url, actors, country)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                movie_data.get("title", ""),
                movie_data.get("genre"),
                movie_data.get("year"),
                movie_data.get("rating"),
                movie_data.get("description", ""),
                movie_data.get("poster_url", ""),
                movie_data.get("actors", ""),
                movie_data.get("country", ""),
            ),
        )

    @staticmethod
    def ensure_actors_column(cursor) -> None:
        """movies tablosunda actors kolonu yoksa ekler (geriye uyumluluk icin)."""
        cursor.execute(
            """
            ALTER TABLE movies
            ADD COLUMN IF NOT EXISTS actors TEXT
            """
        )

    @staticmethod
    def ensure_country_column(cursor) -> None:
        """movies tablosunda country kolonu yoksa ekler (geriye uyumluluk icin)."""
        cursor.execute(
            """
            ALTER TABLE movies
            ADD COLUMN IF NOT EXISTS country TEXT
            """
        )

    @staticmethod
    def get_movies_without_poster(cursor):
        cursor.execute(
            """
            SELECT id, title, year
            FROM movies
            WHERE poster_url IS NULL
               OR poster_url = ''
               OR poster_url = 'N/A'
            ORDER BY title
            """
        )
        return cursor.fetchall()


class OmdbClient:
    """OMDb API istemcisi."""

    BASE_URL = "http://www.omdbapi.com/"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def _request(self, params: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        payload = {"apikey": self.api_key, **params}
        try:
            response = requests.get(self.BASE_URL, params=payload, timeout=10)
            if response.status_code == 401:
                return None, "API Key gecersiz veya yetkisiz. Lutfen API key'i kontrol edin."
            if response.status_code != 200:
                return None, f"HTTP {response.status_code}: {response.reason}"
            data = response.json()
            if data.get("Response") == "False":
                error = data.get("Error", "Bilinmeyen hata")
                if "Invalid API key" in error or "401" in error:
                    return None, "API Key gecersiz! Lutfen dogru API key girin."
                return None, error
            return data, None
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                return None, "API Key gecersiz veya yetkisiz"
            return None, f"HTTP hatasi: {exc}"
        except requests.exceptions.RequestException as exc:
            return None, f"Baglanti hatasi: {exc}"
        except Exception as exc:  # pragma: no cover - korumali blok
            return None, f"Hata: {exc}"

    def test_api_key(self) -> Tuple[bool, str]:
        data, error = self._request({"t": "Inception"})
        if error:
            return False, error
        if not data:
            return False, "Beklenmeyen API cevabi"
        return True, "API Key gecerli"

    def fetch_movie(self, movie_title: str, imdb_id: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any]
        if imdb_id:
            params = {"i": imdb_id, "plot": "full"}
        else:
            params = {"t": movie_title, "type": "movie", "plot": "full"}

        data, error = self._request(params)
        if error:
            return {"error": error}
        if not data:
            return {"error": "Film bilgileri alinamadi"}

        title = data.get("Title", "")
        if not title:
            return {"error": "Film bilgileri alinamadi (baslik yok)"}

        genre_raw = data.get("Genre", "")
        genre = genre_raw.split(",")[0].strip() if genre_raw else None

        year = None
        year_raw = data.get("Year", "")
        if year_raw:
            try:
                year = int(year_raw.split("–")[0])
            except Exception:
                year = None

        rating = None
        rating_raw = data.get("imdbRating", "N/A")
        if rating_raw != "N/A":
            try:
                rating = float(rating_raw)
            except Exception:
                rating = None

        actors = self._normalize_actors(data.get("Actors", ""))
        country = self._normalize_country(data.get("Country", ""))

        return {
            "title": title,
            "genre": genre,
            "year": year,
            "rating": rating,
            "description": data.get("Plot", ""),
            "poster_url": data.get("Poster", ""),
            "actors": actors,
            "country": country,
        }

    @staticmethod
    def _normalize_actors(actors_raw: str, max_actors: int = 4) -> str:
        """OMDb 'Actors' alanini normalize eder: ilk N basrolu virgulle birlestirip dondurur."""
        if not actors_raw or actors_raw.upper() == "N/A":
            return ""

        names = []
        for raw in actors_raw.split(","):
            name = raw.strip()
            if not name or name.upper() == "N/A":
                continue
            names.append(name)
            if len(names) >= max_actors:
                break

        return ", ".join(names)

    @staticmethod
    def _normalize_country(country_raw: str) -> str:
        """OMDb 'Country' alanini normalize eder (orn. 'Turkey, France' -> 'Turkey, France')."""
        if not country_raw or country_raw.upper() == "N/A":
            return ""

        countries = []
        for raw in country_raw.split(","):
            name = raw.strip()
            if not name or name.upper() == "N/A":
                continue
            countries.append(name)

        return ", ".join(countries)

    def fetch_poster(self, movie_title: str, movie_year: Optional[int] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"t": movie_title, "type": "movie"}
        if movie_year:
            params["y"] = movie_year

        data, error = self._request(params)
        if error:
            return {"error": error}
        if not data:
            return {"error": "Poster bilgisi alinamadi"}

        poster_url = data.get("Poster", "")
        if not poster_url or poster_url == "N/A":
            return {"error": "Poster bulunamadi"}

        return {"poster_url": poster_url}
