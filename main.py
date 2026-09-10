import sys
import os
import json
import psycopg2
from psycopg2 import pool
from psycopg2 import OperationalError
import requests
from io import BytesIO
from threading import Thread
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame,
    QMessageBox, QComboBox, QCheckBox, QGridLayout, QSizePolicy,
    QLineEdit, QDialog, QDialogButtonBox, QFormLayout, QTextEdit, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QMetaObject, Q_ARG
from PyQt6.QtGui import QFont, QPixmap


class MovieRecommendationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.selected_movies = []
        self.movie_checkboxes = {}
        self.app_user_key = self.resolve_app_user_key()
        self.profile_file = self.build_profile_file_path()
        self.profile_data = {
            "first_name": "",
            "last_name": "",
            "age": "",
            "gender": "Belirtmek istemiyorum",
            "selected_movies": []
        }
        # Egitilmis icerik tabanli oneri modeli (lazy yuklenir)
        self._content_recommender = None
        self._content_recommender_dirty = False
        self.summary_translation_cache = {}
        self.verified_summary_cache = {}
        # PostgreSQL bağlantı parametreleri
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'movies_db'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', '1234')  # Şifreyi buraya yazın veya environment variable kullanın
        }
        self.connection_pool = None
        # OMDb API Key (https://www.omdbapi.com/apikey.aspx)
        self.omdb_api_key = os.getenv('OMDB_API_KEY', '')  # API key'i buraya yazın veya environment variable kullanın
        self.omdb_base_url = 'http://www.omdbapi.com/'
        self.load_profile_data()
        self.init_database()
        self.init_ui()
        self.apply_styles()
        self.load_random_movies()
    
    def get_connection(self):
        """PostgreSQL bağlantısı al"""
        try:
            if self.connection_pool is None:
                # Bağlantı bilgilerini konsola yazdır (şifre hariç)
                print("=" * 60)
                print("PostgreSQL Baglanti Bilgileri:")
                print(f"  Host: {self.db_config['host']}")
                print(f"  Port: {self.db_config['port']}")
                print(f"  Database: {self.db_config['database']}")
                print(f"  User: {self.db_config['user']}")
                print(f"  Password: {'*' * len(self.db_config['password'])}")
                print("=" * 60)
                
                self.connection_pool = pool.SimpleConnectionPool(1, 10, **self.db_config)
            return self.connection_pool.getconn()
        except OperationalError as e:
            error_msg = str(e)
            print(f"\n[HATA] PostgreSQL baglanti hatasi: {error_msg}\n")
            
            # Hata tipine göre özel mesajlar
            if "could not connect" in error_msg.lower() or "connection refused" in error_msg.lower():
                detailed_msg = (
                    "PostgreSQL sunucusuna baglanilamadi!\n\n"
                    "Olası nedenler:\n"
                    "1. PostgreSQL servisi calismiyor\n"
                    "2. Host veya Port yanlis\n\n"
                    "Cozum:\n"
                    "1. Windows Services'ten PostgreSQL servisini baslatin\n"
                    "2. pgAdmin 4'te sunucunun calistigini kontrol edin"
                )
            elif "authentication failed" in error_msg.lower() or "password" in error_msg.lower():
                detailed_msg = (
                    "Kimlik dogrulama hatasi!\n\n"
                    "Olası nedenler:\n"
                    "1. Kullanici adi yanlis\n"
                    "2. Sifre yanlis\n\n"
                    "Cozum:\n"
                    "1. pgAdmin 4'te kullandiginiz sifreyi kontrol edin\n"
                    "2. main.py dosyasindaki sifreyi guncelleyin\n"
                    "3. Veya environment variable olarak ayarlayin:\n"
                    "   set DB_PASSWORD=sizin_sifreniz"
                )
            elif "database" in error_msg.lower() and "does not exist" in error_msg.lower():
                detailed_msg = (
                    "Veritabani bulunamadi!\n\n"
                    f"'{self.db_config['database']}' veritabani mevcut degil.\n\n"
                    "Cozum:\n"
                    "1. pgAdmin 4'u acin\n"
                    "2. 'movies_db' veritabanini olusturun\n"
                    "3. Veya farkli bir veritabani adi kullanin"
                )
            else:
                detailed_msg = f"Baglanti hatasi:\n{error_msg}"
            
            try:
                QMessageBox.critical(self, "Veritabani Hatasi", 
                                    f"{detailed_msg}\n\n"
                                    f"Detayli hata: {error_msg}")
            except:
                print(f"\nKRITIK: {detailed_msg}\n")
            
            return None
        except Exception as e:
            error_msg = str(e)
            print(f"\n[HATA] Beklenmeyen hata: {error_msg}\n")
            try:
                QMessageBox.critical(self, "Veritabani Hatasi", 
                                    f"Beklenmeyen bir hata olustu:\n{error_msg}\n\n"
                                    f"Lutfen konsol ciktisini kontrol edin.")
            except:
                print(f"\nKRITIK: {error_msg}\n")
            return None
    
    def return_connection(self, conn):
        """Bağlantıyı pool'a geri ver"""
        if self.connection_pool and conn:
            self.connection_pool.putconn(conn)

    def resolve_app_user_key(self):
        """Uygulamayi kullanan kisi icin stabil bir profil anahtari uret."""
        candidate = (
            os.getenv("MOVIERSE_PROFILE_KEY")
            or os.getenv("USERNAME")
            or os.getenv("USER")
            or "default_user"
        )
        cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in candidate.strip().lower())
        return cleaned or "default_user"

    def build_profile_file_path(self):
        """Kullaniciya ozel profil dosyasi yolunu olustur."""
        profiles_dir = os.path.join(os.getcwd(), "user_profiles")
        os.makedirs(profiles_dir, exist_ok=True)
        return os.path.join(profiles_dir, f"{self.app_user_key}_profile.json")
    
    def init_database(self):
        """Veritabanını başlat ve tablo oluştur"""
        try:
            conn = self.get_connection()
            if not conn:
                print("UYARI: Veritabani baglantisi kurulamadi. Uygulama devam edecek ama veri gosterilemeyebilir.")
                return
            
            try:
                cursor = conn.cursor()
                
                # Sadece tablo oluştur (PostgreSQL için)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS movies (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(255) NOT NULL,
                        genre VARCHAR(100),
                        year INTEGER,
                        rating REAL,
                        description TEXT,
                        poster_url TEXT,
                        actors TEXT,
                        country TEXT
                    )
                ''')

                cursor.execute('''
                    ALTER TABLE movies
                    ADD COLUMN IF NOT EXISTS actors TEXT
                ''')

                cursor.execute('''
                    ALTER TABLE movies
                    ADD COLUMN IF NOT EXISTS country TEXT
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS profiles (
                        id SERIAL PRIMARY KEY,
                        profile_key VARCHAR(255) UNIQUE NOT NULL,
                        first_name VARCHAR(100),
                        last_name VARCHAR(100),
                        age VARCHAR(20),
                        gender VARCHAR(50)
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS profile_watched_movies (
                        id SERIAL PRIMARY KEY,
                        profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                        movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
                        watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (profile_id, movie_id)
                    )
                ''')

                # Oneri sistemi icin kategori bazli veri modeli
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS movie_categories (
                        movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
                        category VARCHAR(100) NOT NULL,
                        PRIMARY KEY (movie_id, category)
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS profile_category_preferences (
                        profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                        category VARCHAR(100) NOT NULL,
                        watch_count INTEGER NOT NULL DEFAULT 0,
                        avg_rating REAL,
                        last_watched_at TIMESTAMP,
                        PRIMARY KEY (profile_id, category)
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS interaction_events (
                        id SERIAL PRIMARY KEY,
                        profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                        movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
                        event_type VARCHAR(30) NOT NULL,
                        event_value REAL,
                        event_source VARCHAR(50) NOT NULL DEFAULT 'app',
                        occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (profile_id, movie_id, event_type, event_source)
                    )
                ''')

                cursor.execute('CREATE INDEX IF NOT EXISTS idx_movie_categories_category ON movie_categories (category)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_profile_watched_movies_profile_id ON profile_watched_movies (profile_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_profile_watched_movies_movie_id ON profile_watched_movies (movie_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_movies_title_lower ON movies (LOWER(title))')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_movies_year_rating ON movies (year, rating)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_interaction_events_profile_id ON interaction_events (profile_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_interaction_events_movie_id ON interaction_events (movie_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_interaction_events_type_time ON interaction_events (event_type, occurred_at)')

                cursor.execute('''
                    CREATE OR REPLACE VIEW recommendation_training_data AS
                    SELECT
                        pwm.profile_id,
                        pwm.movie_id,
                        mc.category,
                        COALESCE(m.rating, 0) AS movie_rating,
                        pwm.watched_at
                    FROM profile_watched_movies pwm
                    JOIN movies m ON m.id = pwm.movie_id
                    LEFT JOIN movie_categories mc ON mc.movie_id = m.id
                ''')

                cursor.execute('''
                    CREATE OR REPLACE VIEW ml_training_interactions AS
                    SELECT
                        ie.profile_id AS user_id,
                        ie.movie_id AS item_id,
                        ie.event_type,
                        CASE WHEN ie.event_type = 'watched' THEN 1 ELSE 0 END AS label,
                        COALESCE(ie.event_value, m.rating, 0) AS target_value,
                        COALESCE(m.rating, 0) AS movie_rating,
                        COALESCE(m.year, 0) AS movie_year,
                        COALESCE(m.genre, '') AS raw_genre,
                        ARRAY_REMOVE(ARRAY_AGG(DISTINCT mc.category), NULL) AS categories,
                        ie.occurred_at
                    FROM interaction_events ie
                    JOIN movies m ON m.id = ie.movie_id
                    LEFT JOIN movie_categories mc ON mc.movie_id = m.id
                    GROUP BY
                        ie.profile_id, ie.movie_id, ie.event_type, ie.event_value, ie.occurred_at,
                        m.rating, m.year, m.genre
                ''')

                cursor.execute('''
                    CREATE OR REPLACE VIEW ml_profile_feature_vectors AS
                    SELECT
                        p.id AS profile_id,
                        p.profile_key,
                        COUNT(DISTINCT pwm.movie_id) AS watched_movie_count,
                        COALESCE(AVG(m.rating), 0) AS avg_watched_rating,
                        COALESCE(MAX(pwm.watched_at), CURRENT_TIMESTAMP) AS last_activity_at,
                        COALESCE(
                            JSONB_OBJECT_AGG(pcp.category, pcp.watch_count)
                            FILTER (WHERE pcp.category IS NOT NULL),
                            '{}'::jsonb
                        ) AS category_watch_histogram
                    FROM profiles p
                    LEFT JOIN profile_watched_movies pwm ON pwm.profile_id = p.id
                    LEFT JOIN movies m ON m.id = pwm.movie_id
                    LEFT JOIN profile_category_preferences pcp ON pcp.profile_id = p.id
                    GROUP BY p.id, p.profile_key
                ''')

                self.refresh_recommendation_features(cursor=cursor, rebuild_movie_categories=True)
                self.refresh_ml_training_assets(cursor=cursor)
                
                conn.commit()
                print("Veritabani tablosu hazir.")
            except Exception as e:
                conn.rollback()
                error_msg = f"Veritabani baslatilirken hata olustu:\n{str(e)}"
                print(f"HATA: {error_msg}")
                try:
                    QMessageBox.critical(self, "Veritabani Hatasi", 
                                        f"{error_msg}\n\n"
                                        f"Lutfen pgAdmin 4'te movies_db veritabaninin olusturuldugundan emin olun.")
                except:
                    pass
            finally:
                self.return_connection(conn)
        except Exception as e:
            print(f"KRITIK HATA: Veritabani baglantisi kurulamadi: {str(e)}")
            try:
                QMessageBox.critical(self, "Kritik Hata", 
                                    f"PostgreSQL baglantisi kurulamadi:\n{str(e)}\n\n"
                                    f"Lutfen:\n"
                                    f"1. PostgreSQL servisinin calistigindan emin olun\n"
                                    f"2. pgAdmin 4'te movies_db veritabaninin olusturuldugundan emin olun\n"
                                    f"3. Baglanti bilgilerini kontrol edin")
            except:
                pass

    def refresh_recommendation_features(self, cursor=None, rebuild_movie_categories=False):
        """
        Oneri sistemi icin kategori ve profil ozellik tablolarini guncelle.
        rebuild_movie_categories=True ise film-kategori map'i bastan kurulur.
        """
        owns_connection = False
        conn = None

        if cursor is None:
            conn = self.get_connection()
            if not conn:
                return
            cursor = conn.cursor()
            owns_connection = True

        try:
            if rebuild_movie_categories:
                cursor.execute("DELETE FROM movie_categories")
                cursor.execute("""
                    INSERT INTO movie_categories (movie_id, category)
                    SELECT
                        m.id,
                        INITCAP(TRIM(cat.value)) AS category
                    FROM movies m
                    CROSS JOIN LATERAL UNNEST(string_to_array(COALESCE(m.genre, ''), ',')) AS cat(value)
                    WHERE TRIM(cat.value) != ''
                    ON CONFLICT (movie_id, category) DO NOTHING
                """)

            cursor.execute("DELETE FROM profile_category_preferences")
            cursor.execute("""
                INSERT INTO profile_category_preferences (
                    profile_id, category, watch_count, avg_rating, last_watched_at
                )
                SELECT
                    pwm.profile_id,
                    mc.category,
                    COUNT(*)::INTEGER AS watch_count,
                    AVG(m.rating) AS avg_rating,
                    MAX(pwm.watched_at) AS last_watched_at
                FROM profile_watched_movies pwm
                JOIN movies m ON m.id = pwm.movie_id
                JOIN movie_categories mc ON mc.movie_id = m.id
                GROUP BY pwm.profile_id, mc.category
            """)

            if owns_connection:
                conn.commit()
        except Exception:
            if owns_connection and conn:
                conn.rollback()
            raise
        finally:
            if owns_connection and conn:
                self.return_connection(conn)

    def refresh_ml_training_assets(self, cursor=None):
        """
        ML egitimi icin etkileşim tablosunu profile_watched_movies verisi ile senkronize et.
        """
        owns_connection = False
        conn = None

        if cursor is None:
            conn = self.get_connection()
            if not conn:
                return
            cursor = conn.cursor()
            owns_connection = True

        try:
            cursor.execute("""
                INSERT INTO interaction_events (profile_id, movie_id, event_type, event_value, event_source, occurred_at)
                SELECT
                    pwm.profile_id,
                    pwm.movie_id,
                    'watched' AS event_type,
                    m.rating AS event_value,
                    'app_watch_confirmed' AS event_source,
                    pwm.watched_at
                FROM profile_watched_movies pwm
                JOIN movies m ON m.id = pwm.movie_id
                ON CONFLICT (profile_id, movie_id, event_type, event_source) DO NOTHING
            """)

            if owns_connection:
                conn.commit()
        except Exception:
            if owns_connection and conn:
                conn.rollback()
            raise
        finally:
            if owns_connection and conn:
                self.return_connection(conn)
    
    def get_content_recommender(self, force_retrain=False):
        """
        Egitilmis icerik tabanli oneri modelini dondurur.

        - Bellekte cache'lenir.
        - Disk'te yoksa veya force_retrain=True ise sifirdan egitir.
        - Yeni film/profil etkilesimi olduktan sonra dirty=True ise yeniden egitir.
        """
        try:
            from ml import ContentRecommender
            from ml.train import train_and_save
        except ImportError as exc:
            QMessageBox.critical(
                self,
                "ML Modulu Eksik",
                "Oneri motoru icin gerekli paketler eksik.\n\n"
                "Su komutu calistirin:\n"
                "  pip install -r requirements.txt\n\n"
                f"Hata: {exc}"
            )
            return None

        if self._content_recommender is not None and not (force_retrain or self._content_recommender_dirty):
            return self._content_recommender

        model_path = ContentRecommender.DEFAULT_MODEL_PATH

        if not force_retrain and not self._content_recommender_dirty and os.path.exists(model_path):
            try:
                self._content_recommender = ContentRecommender.load(model_path)
                return self._content_recommender
            except Exception as exc:
                print(f"[WARN] Mevcut model yuklenemedi, yeniden egitiliyor: {exc}")

        try:
            self.statusBar().showMessage("Oneri modeli egitiliyor, lutfen bekleyin...")
            QApplication.processEvents()
            recommender = train_and_save(verbose=False)
            self._content_recommender = recommender
            self._content_recommender_dirty = False
            self.statusBar().showMessage(
                f"Oneri modeli hazir: {recommender.stats.movie_count} film, "
                f"{recommender.stats.feature_dim} ozellik"
            )
            return recommender
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Egitim Hatasi",
                f"Oneri modeli egitilirken hata olustu:\n{exc}"
            )
            return None

    def mark_content_recommender_dirty(self):
        """Veritabani/profil degisikliginden sonra cagrilir; sonraki istekte yeniden egitilir."""
        self._content_recommender_dirty = True

    @staticmethod
    def _normalize_actor_list(actors_raw, max_actors=4):
        """OMDb 'Actors' alanini virgulle ayirip ilk N basrolu birlestirir."""
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
    def _normalize_country_value(country_raw):
        """OMDb 'Country' alanini virgulle ayirip temiz string olarak dondurur."""
        if not country_raw or country_raw.upper() == "N/A":
            return ""

        countries = []
        for raw in country_raw.split(","):
            name = raw.strip()
            if not name or name.upper() == "N/A":
                continue
            countries.append(name)
        return ", ".join(countries)

    def get_random_movies(self, limit=100):
        """Veritabanından rastgele filmler getir"""
        conn = self.get_connection()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM movies')
            total_movies = cursor.fetchone()[0]
            
            if total_movies == 0:
                return []
            
            # Rastgele 100 film seç (eğer 100'den az varsa hepsini al)
            actual_limit = min(limit, total_movies)
            cursor.execute('SELECT id, title, genre, year, rating, description, poster_url FROM movies ORDER BY RANDOM() LIMIT %s', (actual_limit,))
            movies = cursor.fetchall()
            
            return movies
        except Exception as e:
            QMessageBox.critical(self, "Veritabanı Hatası", 
                                f"Filmler getirilirken hata oluştu:\n{str(e)}")
            return []
        finally:
            self.return_connection(conn)
    
    def init_ui(self):
        self.setWindowTitle("MOVIERSE")
        self.setGeometry(100, 100, 1400, 900)
        
        central_widget = QWidget()
        central_widget.setStyleSheet("background-color: #0f1419;")
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Profesyonel header tasarımı
        header_widget = QFrame()
        header_widget.setStyleSheet("""
            QFrame { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #090f1f, 
                    stop:0.25 #111b33, 
                    stop:0.5 #182448, 
                    stop:0.75 #121d39, 
                    stop:1 #090f1f); 
                padding: 0px; 
                border: none;
                border-bottom: 2px solid #3347b0;
            }
        """)
        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(60, 45, 60, 35)
        header_layout.setSpacing(0)
        
        # Üst bar - istatistikler ve bilgiler
        top_bar = QWidget()
        top_bar.setStyleSheet("background-color: transparent;")
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 0, 0, 15)
        top_bar_layout.setSpacing(20)

        # Sol tarafta logo ve başlık
        brand_container = QWidget()
        brand_container.setStyleSheet("background-color: transparent;")
        brand_layout = QHBoxLayout()
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(18)
        
        # Logo container - daha profesyonel
        logo_container = QFrame()
        logo_container.setFixedSize(60, 60)
        logo_container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #38bdf8, 
                    stop:1 #7c3aed);
                border-radius: 15px;
                border: 2px solid rgba(96, 165, 250, 0.45);
            }
        """)
        logo_layout = QVBoxLayout()
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label = QLabel("🎬")
        logo_label.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setStyleSheet("color: #ffffff; padding: 0px; margin: 0px;")
        logo_layout.addWidget(logo_label)
        logo_container.setLayout(logo_layout)
        brand_layout.addWidget(logo_container)
        
        # Marka metni
        brand_text_container = QWidget()
        brand_text_container.setStyleSheet("background-color: transparent;")
        brand_text_layout = QVBoxLayout()
        brand_text_layout.setContentsMargins(0, 0, 0, 0)
        brand_text_layout.setSpacing(6)
        
        title_label = QLabel("MOVIERSE")
        title_label.setFont(QFont("Segoe UI", 38, QFont.Weight.Bold))
        title_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                padding: 0px;
                margin: 0px;
                letter-spacing: 5px;
                background: transparent;
            }
        """)
        brand_text_layout.addWidget(title_label)
        
        subtitle_label = QLabel("AI-Powered Movie Discovery Platform")
        subtitle_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Normal))
        subtitle_label.setStyleSheet("color: #94a3b8; padding: 0px; margin: 0px; font-weight: 400; letter-spacing: 1px;")
        brand_text_layout.addWidget(subtitle_label)
        
        brand_text_container.setLayout(brand_text_layout)
        brand_layout.addWidget(brand_text_container)
        
        brand_container.setLayout(brand_layout)
        top_bar_layout.addWidget(brand_container, 0, Qt.AlignmentFlag.AlignLeft)
        top_bar_layout.addStretch(1)

        # Ust menunun ortasinda film oneri butonu
        center_recommend_button = QPushButton("🎬 Film Oner")
        center_recommend_button.setCursor(Qt.CursorShape.PointingHandCursor)
        center_recommend_button.setFixedHeight(46)
        center_recommend_button.setMinimumWidth(190)
        center_recommend_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:0.5 #3b82f6, stop:1 #8b5cf6);
                color: #ffffff;
                padding: 10px 24px;
                border-radius: 12px;
                font-size: 15px;
                font-weight: 800;
                border: 1px solid rgba(255, 255, 255, 0.35);
                letter-spacing: 0.6px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:0.5 #2563eb, stop:1 #7c3aed);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e40af, stop:0.5 #1d4ed8, stop:1 #6d28d9);
            }
        """)
        center_recommend_button.clicked.connect(self.show_recommendation_dialog)
        top_bar_layout.addWidget(center_recommend_button, 0, Qt.AlignmentFlag.AlignCenter)
        top_bar_layout.addStretch(1)
        
        # Sağ taraftaki aksiyon butonları ayrı bir yardımcı metodda oluşturuluyor.
        actions_container = self.build_header_actions()
        top_bar_layout.addWidget(actions_container, 0, Qt.AlignmentFlag.AlignRight)
        
        top_bar.setLayout(top_bar_layout)
        header_layout.addWidget(top_bar)
        
        # Alt çizgi - profesyonel görünüm
        bottom_line = QFrame()
        bottom_line.setFrameShape(QFrame.Shape.HLine)
        bottom_line.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 transparent, 
                    stop:0.3 #38bdf8, 
                    stop:0.7 #7c3aed, 
                    stop:1 transparent);
                max-height: 1px;
                margin: 0px;
            }
        """)
        bottom_line.setFixedHeight(1)
        header_layout.addWidget(bottom_line)
        
        header_widget.setLayout(header_layout)
        main_layout.addWidget(header_widget)
        
        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        main_scroll.setStyleSheet("QScrollArea { border: none; background-color: #0f1419; } QScrollArea > QWidget > QWidget { background-color: #0f1419; } QScrollBar:vertical { border: none; background: #1a1f2e; width: 12px; border-radius: 6px; margin: 0px; } QScrollBar::handle:vertical { background: #2d3748; border-radius: 6px; min-height: 40px; margin: 2px; } QScrollBar::handle:vertical:hover { background: #3b82f6; } QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }")
        
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #0f1419;")
        content_layout = QHBoxLayout()
        content_layout.setSpacing(28)
        content_layout.setContentsMargins(45, 35, 45, 35)
        
        left_widget = QWidget()
        left_widget.setStyleSheet("background-color: #0f1419;")
        left_layout = QVBoxLayout()
        left_layout.setSpacing(22)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        movie_selection_container = QFrame()
        movie_selection_container.setStyleSheet("QFrame { background-color: #151d33; border-radius: 20px; padding: 0px; border: 2px solid #304267; }")
        movie_selection_layout = QVBoxLayout()
        movie_selection_layout.setSpacing(0)
        movie_selection_layout.setContentsMargins(0, 0, 0, 0)
        
        movie_selection_header = QWidget()
        movie_selection_header.setStyleSheet("background-color: transparent;")
        header_layout = QVBoxLayout()
        header_layout.setSpacing(14)
        header_layout.setContentsMargins(28, 28, 28, 20)
        
        selection_label = QLabel("✅ İzlediğiniz Filmleri Seçin")
        selection_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        selection_label.setStyleSheet("color: #60a5fa; font-weight: 700; letter-spacing: 0.6px; padding-bottom: 12px; border-bottom: 2px solid #304267; margin: 0px;")
        header_layout.addWidget(selection_label)
        
        info_label = QLabel("Veritabanından rastgele 100 film gösteriliyor. İzlediğiniz filmleri işaretleyin.")
        info_label.setFont(QFont("Segoe UI", 11))
        info_label.setStyleSheet("color: #94a3b8; padding: 8px 0px; line-height: 1.5;")
        info_label.setWordWrap(True)
        header_layout.addWidget(info_label)
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.refresh_button = QPushButton("🔄 Yeni Filmler Yükle")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.setStyleSheet("QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0ea5e9, stop:1 #3b82f6); color: #ffffff; padding: 10px 20px; border-radius: 10px; font-size: 13px; font-weight: 700; border: none; } QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #2563eb); } QPushButton:pressed { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369a1, stop:1 #1d4ed8); }")
        self.refresh_button.clicked.connect(self.load_random_movies)
        button_layout.addWidget(self.refresh_button)
        
        self.save_button = QPushButton("💾 Seçilenleri Kaydet")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.setStyleSheet("QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #7c3aed); color: #ffffff; padding: 10px 20px; border-radius: 10px; font-size: 13px; font-weight: 700; border: none; } QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4338ca, stop:1 #6d28d9); } QPushButton:pressed { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3730a3, stop:1 #5b21b6); }")
        self.save_button.clicked.connect(self.save_selected_movies)
        button_layout.addWidget(self.save_button)
        
        button_layout.addStretch()
        header_layout.addLayout(button_layout)
        
        movie_selection_header.setLayout(header_layout)
        movie_selection_layout.addWidget(movie_selection_header)

        self.movies_widget = QWidget()
        self.movies_widget.setStyleSheet("background-color: transparent;")
        self.movies_layout = QGridLayout()
        self.movies_layout.setSpacing(10)
        self.movies_layout.setContentsMargins(20, 20, 20, 20)
        self.movies_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.movies_widget.setLayout(self.movies_layout)
        
        movies_scroll_widget = QWidget()
        movies_scroll_widget.setStyleSheet("background-color: transparent;")
        movies_scroll_layout = QVBoxLayout()
        movies_scroll_layout.setContentsMargins(0, 0, 0, 0)
        movies_scroll_layout.addWidget(self.movies_widget)
        movies_scroll_widget.setLayout(movies_scroll_layout)
        movie_selection_layout.addWidget(movies_scroll_widget)
        
        movie_selection_container.setLayout(movie_selection_layout)
        left_layout.addWidget(movie_selection_container)
        
        left_widget.setLayout(left_layout)
        left_widget.setMaximumWidth(1090)  # Sol tarafı büyüt
        content_layout.addWidget(left_widget, 2)
        
        right_widget = QWidget()
        right_widget.setMaximumWidth(330)
        right_widget.setMinimumWidth(290)
        right_widget.setStyleSheet("background-color: #0f1419;")
        right_layout = QVBoxLayout()
        right_layout.setSpacing(0)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Sağ taraftaki kategori ve film listesini birleştir
        unified_right_container = QFrame()
        unified_right_container.setStyleSheet("QFrame { background-color: #151d33; border-radius: 20px; padding: 0px; border: 2px solid #304267; }")
        unified_right_layout = QVBoxLayout()
        unified_right_layout.setSpacing(0)
        unified_right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Üst kısım: Kategori seçimi
        category_header = QWidget()
        category_header.setStyleSheet("background-color: transparent;")
        category_header_layout = QVBoxLayout()
        category_header_layout.setSpacing(12)
        category_header_layout.setContentsMargins(20, 20, 20, 16)
        
        category_label = QLabel("🎭 Kategori Seç")
        category_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        category_label.setStyleSheet("color: #60a5fa; font-weight: 700; letter-spacing: 0.6px; padding-bottom: 10px; border-bottom: 2px solid #304267; margin: 0px;")
        category_header_layout.addWidget(category_label)
        
        self.category_combo = QComboBox()
        # Kategorileri veritabanından dinamik olarak yükle
        categories = self.load_categories_from_db()
        self.category_combo.addItems(categories)
        self.category_combo.setStyleSheet("QComboBox { background-color: #0f172a; color: #e2e8f0; padding: 10px 14px; border: 2px solid #304267; border-radius: 10px; font-size: 13px; font-weight: 500; } QComboBox:hover { border: 2px solid #60a5fa; background-color: #17223c; } QComboBox:focus { border: 2px solid #60a5fa; background-color: #17223c; } QComboBox::drop-down { border: none; padding-right: 12px; } QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #60a5fa; margin-right: 4px; } QComboBox QAbstractItemView { background-color: #17223c; border: 2px solid #304267; border-radius: 10px; color: #e2e8f0; selection-background-color: #304267; selection-color: #60a5fa; padding: 4px; }")
        self.category_combo.currentTextChanged.connect(self.on_category_changed)
        category_header_layout.addWidget(self.category_combo)
        
        category_header.setLayout(category_header_layout)
        unified_right_layout.addWidget(category_header)
        
        # Ayırıcı
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #304267; max-height: 1px; margin: 0px 20px;")
        separator.setFixedHeight(1)
        unified_right_layout.addWidget(separator)
        
        # Alt kısım: Film listesi
        popular_header = QWidget()
        popular_header.setStyleSheet("background-color: transparent;")
        popular_header_layout = QVBoxLayout()
        popular_header_layout.setSpacing(12)
        popular_header_layout.setContentsMargins(20, 16, 20, 16)
        
        popular_label = QLabel("🎬 Kategoriye Göre Filmler")
        popular_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        popular_label.setStyleSheet("color: #60a5fa; font-weight: 700; letter-spacing: 0.6px; padding-bottom: 10px; border-bottom: 2px solid #304267; margin: 0px;")
        popular_header_layout.addWidget(popular_label)
        
        popular_header.setLayout(popular_header_layout)
        unified_right_layout.addWidget(popular_header)
        
        popular_layout = QVBoxLayout()
        popular_layout.setSpacing(0)
        popular_layout.setContentsMargins(0, 0, 0, 0)
        
        popular_scroll = QScrollArea()
        popular_scroll.setWidgetResizable(True)
        popular_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        popular_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        popular_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; } QScrollArea > QWidget > QWidget { background-color: transparent; } QScrollBar:vertical { border: none; background: #1a1f2e; width: 8px; border-radius: 4px; } QScrollBar::handle:vertical { background: #2d3748; border-radius: 4px; min-height: 25px; } QScrollBar::handle:vertical:hover { background: #3b82f6; } QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }")
        popular_scroll.setMinimumHeight(350)
        
        self.popular_widget = QWidget()
        self.popular_widget.setStyleSheet("background-color: transparent;")
        self.popular_layout = QVBoxLayout()
        self.popular_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.popular_layout.setSpacing(8)
        self.popular_layout.setContentsMargins(20, 0, 20, 20)
        self.popular_widget.setLayout(self.popular_layout)
        
        popular_scroll.setWidget(self.popular_widget)
        popular_layout.addWidget(popular_scroll)
        
        unified_right_layout.addLayout(popular_layout)

        unified_right_container.setLayout(unified_right_layout)
        right_layout.addWidget(unified_right_container, 1)
        
        right_widget.setLayout(right_layout)
        content_layout.addWidget(right_widget, 1)
        
        content_widget.setLayout(content_layout)
        main_scroll.setWidget(content_widget)
        main_layout.addWidget(main_scroll)
        central_widget.setLayout(main_layout)
        
        self.statusBar().setStyleSheet("QStatusBar { background-color: #1a1f2e; color: #94a3b8; border-top: 2px solid #2d3748; padding: 8px 12px; font-size: 12px; font-weight: 400; }")
        self.statusBar().showMessage("Hazır - İzlediğiniz filmleri seçin")
        
        # İlk açılışta kategorileri yükle
        self.update_popular_movies("Tümü")
    
    def apply_styles(self):
        self.setStyleSheet("QMainWindow { background-color: #0b1120; } QMessageBox { background-color: #151d33; color: #e2e8f0; } QMessageBox QLabel { background-color: #151d33; color: #e2e8f0; padding: 10px; } QMessageBox QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #4f46e5); color: #ffffff; padding: 8px 20px; border-radius: 8px; font-size: 13px; font-weight: 700; border: none; min-width: 80px; } QMessageBox QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #4338ca); } QMessageBox QPushButton:pressed { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e40af, stop:1 #3730a3); }")

    def create_header_action_button(self, icon, tooltip, primary=False, on_click=None):
        button = QPushButton(icon)
        button.setFixedSize(36, 36)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(tooltip)

        if primary:
            button.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #38bdf8, stop:1 #7c3aed);
                    border: 1px solid rgba(96, 165, 250, 0.6);
                    border-radius: 8px;
                    color: #ffffff;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0ea5e9, stop:1 #6d28d9);
                    border: 1px solid rgba(125, 211, 252, 0.75);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0369a1, stop:1 #5b21b6);
                }
            """)
        else:
            button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(96, 165, 250, 0.12);
                    border: 1px solid rgba(96, 165, 250, 0.4);
                    border-radius: 8px;
                    color: #7dd3fc;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background-color: rgba(96, 165, 250, 0.2);
                    border: 1px solid rgba(96, 165, 250, 0.6);
                }
                QPushButton:pressed {
                    background-color: rgba(96, 165, 250, 0.28);
                }
            """)

        if on_click:
            button.clicked.connect(on_click)

        return button

    def build_header_actions(self):
        actions_container = QWidget()
        actions_container.setStyleSheet("background-color: transparent;")
        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)

        actions_layout.addWidget(
            self.create_header_action_button(
                "🔍",
                "OMDb'den Film Ara ve Ekle",
                on_click=self.show_omdb_search_dialog
            )
        )
        actions_layout.addWidget(
            self.create_header_action_button(
                "🧠",
                "Ozetleri Dogrula ve Guncelle",
                on_click=self.update_movie_summaries_from_omdb
            )
        )
        actions_layout.addWidget(
            self.create_header_action_button("👤", "Profil", primary=True, on_click=self.show_profile_dialog)
        )

        actions_container.setLayout(actions_layout)
        return actions_container
    
    def load_random_movies(self):
        """Rastgele 100 filmi yükle ve checkbox'larla göster"""
        grid_columns = 4

        # Önceki filmleri temizle
        try:
            while self.movies_layout.count():
                item = self.movies_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        except:
            pass
        
        self.movie_checkboxes.clear()
        # Kural: oylama yalnizca secili film icin gecerlidir; secim oturum bazli
        # oldugundan her yeniden yuklemede onceki oylar temizlenir.
        cleared = self.clear_all_reactions_for_current_profile()
        if cleared:
            print(f"[load_random_movies] Onceki {cleared} oy temizlendi (secim oturum bazli)")
        # Reaksiyonlar temizlendi; butonlar bos baslayacak
        current_reactions = {}
        movies = self.get_random_movies(100)
        
        if not movies:
            empty_label = QLabel("Veritabanında film bulunamadı.\nLütfen önce veritabanına film ekleyin.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #64748b; font-size: 14px; padding: 40px 20px; line-height: 1.8; background-color: #0f1419; border-radius: 12px; border: 2px dashed #2d3748;")
            empty_label.setWordWrap(True)
            self.movies_layout.addWidget(empty_label, 0, 0, 1, grid_columns)  # Grid'de tum sutunlari kaplar
            self.statusBar().showMessage("Veritabanında film yok")
            return
        
        # Grid sisteminde filmleri göster (her satırda 4 film)
        columns = grid_columns
        row = 0
        col = 0
        
        for movie_data in movies:
            movie_id = movie_data[0]
            title = movie_data[1]
            genre = movie_data[2] if len(movie_data) > 2 else None
            year = movie_data[3] if len(movie_data) > 3 else None
            rating = movie_data[4] if len(movie_data) > 4 else None
            description = movie_data[5] if len(movie_data) > 5 else None
            poster_url = movie_data[6] if len(movie_data) > 6 else None
            
            # Her film için ayrı kart oluştur (biraz daha geniş)
            card_width = 240
            card_horizontal_padding = 24  # Sol+sağ içerik padding toplamı (12 + 12)
            poster_width = 200
            poster_height = 260

            movie_card = QFrame()
            movie_card.setFixedWidth(card_width)
            # Sabit yukseklik: tum kartlar ayni boyutta -> grid duzgun hizalanir
            movie_card.setFixedHeight(470)
            movie_card.setStyleSheet("""
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #18233b, stop:1 #101827);
                    border: 2px solid #304267;
                    border-radius: 12px;
                    margin: 4px;
                }
                QFrame:hover {
                    border: 2px solid #60a5fa;
                }
            """)

            card_layout = QVBoxLayout()
            card_layout.setSpacing(6)
            card_layout.setContentsMargins(12, 12, 12, 12)
            
            # Film afişi - async yükleme için placeholder önce göster
            # Poster URL validasyonu: boş, None, "N/A" veya geçersiz URL kontrolü
            is_valid_poster_url = (poster_url and 
                                  poster_url.strip() != '' and 
                                  poster_url.strip().upper() != 'N/A' and
                                  (poster_url.startswith('http://') or poster_url.startswith('https://')))
            
            if is_valid_poster_url:
                poster_label = QLabel()
                poster_label.setFixedSize(poster_width, poster_height)
                poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                poster_label.setStyleSheet("""
                    QLabel {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1f2e, stop:1 #0f1419);
                        border: 2px solid #2d3748;
                        border-radius: 8px;
                    }
                """)
                poster_label.setScaledContents(False)
                poster_label.setText("🎬")
                poster_label.setStyleSheet("""
                    QLabel {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1f2e, stop:1 #0f1419);
                        border: 2px solid #2d3748;
                        border-radius: 8px;
                        color: #64748b;
                        font-size: 48px;
                    }
                """)
                
                # Poster'i arka planda yükle (performans için) - retry mekanizması ile
                def load_poster_async(url, label):
                    max_retries = 2
                    for attempt in range(max_retries):
                        try:
                            response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'}, stream=True)
                            if response.status_code == 200:
                                # Content-Type kontrolü
                                content_type = response.headers.get('Content-Type', '')
                                if 'image' not in content_type:
                                    if attempt < max_retries - 1:
                                        time.sleep(0.5)
                                        continue
                                    break
                                
                                pixmap = QPixmap()
                                pixmap.loadFromData(response.content)
                                if not pixmap.isNull():
                                    # Tum posterleri ayni olcude gostermek icin
                                    # resmi buyutup merkezden kirpiyoruz.
                                    filled_pixmap = pixmap.scaled(
                                        poster_width,
                                        poster_height,
                                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                        Qt.TransformationMode.SmoothTransformation
                                    )
                                    x_offset = max(0, (filled_pixmap.width() - poster_width) // 2)
                                    y_offset = max(0, (filled_pixmap.height() - poster_height) // 2)
                                    scaled_pixmap = filled_pixmap.copy(x_offset, y_offset, poster_width, poster_height)
                                    # Thread-safe UI güncellemesi
                                    QMetaObject.invokeMethod(label, "setPixmap", Qt.ConnectionType.QueuedConnection, Q_ARG(QPixmap, scaled_pixmap))
                                    QMetaObject.invokeMethod(label, "setStyleSheet", Qt.ConnectionType.QueuedConnection, 
                                        Q_ARG(str, """
                                            QLabel {
                                                background-color: transparent;
                                                border: 2px solid #2d3748;
                                                border-radius: 8px;
                                            }
                                        """))
                                    return  # Başarılı, çık
                                else:
                                    if attempt < max_retries - 1:
                                        time.sleep(0.5)
                                        continue
                        except requests.exceptions.Timeout:
                            if attempt < max_retries - 1:
                                time.sleep(1)
                                continue
                        except requests.exceptions.RequestException:
                            if attempt < max_retries - 1:
                                time.sleep(0.5)
                                continue
                        except Exception:
                            if attempt < max_retries - 1:
                                time.sleep(0.5)
                                continue
                        break  # Tüm denemeler başarısız
                
                Thread(target=load_poster_async, args=(poster_url, poster_label), daemon=True).start()
                card_layout.addWidget(poster_label)
            else:
                # Poster yoksa placeholder göster
                poster_label = QLabel()
                poster_label.setFixedSize(poster_width, poster_height)
                poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                poster_label.setStyleSheet("""
                    QLabel {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1f2e, stop:1 #0f1419);
                        border: 2px solid #2d3748;
                        border-radius: 8px;
                        color: #64748b;
                        font-size: 48px;
                    }
                """)
                poster_label.setText("🎬")
                card_layout.addWidget(poster_label)
            
            # Film başlığı ve checkbox - afişin altında düzgün görünsün
            title_container = QWidget()
            title_container.setStyleSheet("background-color: transparent;")
            title_container_layout = QHBoxLayout()
            title_container_layout.setSpacing(8)
            title_container_layout.setContentsMargins(0, 6, 0, 0)  # Afişten sonra küçük boşluk
            
            # Modern "Izledim" sec butonu - dairesel toggle tasarimi
            checkbox = QPushButton()
            checkbox.setCheckable(True)
            checkbox.setFixedSize(32, 32)
            checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
            checkbox.setToolTip("Izledim - bu filmi profile ekle")

            select_style_inactive = """
                QPushButton {
                    background-color: rgba(15, 23, 42, 0.85);
                    color: transparent;
                    border: 2px solid #475569;
                    border-radius: 16px;
                    font-size: 14px;
                    font-weight: 900;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: rgba(34, 197, 94, 0.18);
                    border: 2px solid #22c55e;
                    color: rgba(187, 247, 208, 0.9);
                }
            """
            # AKTIF: solid parlak yesil + beyaz tik - secildigi her durumda net belli olur
            select_style_active = """
                QPushButton {
                    background-color: #16a34a;
                    color: #ffffff;
                    border: 3px solid #4ade80;
                    border-radius: 16px;
                    font-size: 18px;
                    font-weight: 900;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #15803d;
                    border: 3px solid #86efac;
                }
            """

            def apply_select_style():
                if checkbox.isChecked():
                    checkbox.setText("✓")
                    checkbox.setStyleSheet(select_style_active)
                else:
                    checkbox.setText("")
                    checkbox.setStyleSheet(select_style_inactive)

            apply_select_style()

            # NOT: on_checkbox_changed tanimi/baglama, oylama butonlari kurulduktan
            # sonra (asagida) yapilir; cunku secimi acip/kapatmak oylama butonlarinin
            # aktif/pasif durumunu da degistirir.

            title_container_layout.addWidget(checkbox)
            
            # Film başlığı - sade, secim butonu one ciksin diye agir stil kullanma
            title_label = QLabel(title)
            title_label.setWordWrap(True)
            title_label.setFixedHeight(42)
            title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            title_label.setStyleSheet("""
                QLabel {
                    color: #ffffff;
                    font-size: 13px;
                    font-weight: 700;
                    padding: 2px 4px;
                    background: transparent;
                    line-height: 1.3;
                }
            """)
            title_font = QFont("Segoe UI", 13, QFont.Weight.Bold)
            title_label.setFont(title_font)
            title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            title_container_layout.addWidget(title_label, 1)

            # Detay butonu - tiklayinca film ozet/bilgi diyalogu acar (secimi etkilemez)
            detail_button = QPushButton("i")
            detail_button.setFixedSize(28, 28)
            detail_button.setCursor(Qt.CursorShape.PointingHandCursor)
            detail_button.setToolTip("Film detayini goster (ozet, tur, puan)")
            detail_button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(59, 130, 246, 0.15);
                    color: #93c5fd;
                    border: 2px solid #3b82f6;
                    border-radius: 14px;
                    font-size: 14px;
                    font-weight: 900;
                    font-style: italic;
                    font-family: 'Georgia', serif;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #3b82f6;
                    color: #ffffff;
                    border: 2px solid #60a5fa;
                }
                QPushButton:pressed {
                    background-color: #1d4ed8;
                    border: 2px solid #2563eb;
                }
            """)

            def on_detail_clicked(_=False, mid=movie_id, t=title, g=genre,
                                  y=year, r=rating, d=description):
                self.show_movie_info_dialog(
                    movie_id=mid, title=t, genre=g, year=y,
                    rating=r, description=d
                )

            detail_button.clicked.connect(on_detail_clicked)
            title_container_layout.addWidget(detail_button)

            title_container.setLayout(title_container_layout)
            card_layout.addWidget(title_container)
            
            # Film bilgileri (tür, yıl) - daha belirgin rozetler
            info_layout = QHBoxLayout()
            info_layout.setSpacing(6)
            info_layout.setContentsMargins(0, 4, 0, 0)  # Checkbox zaten title_container içinde
            
            if genre:
                # Tur metni cok uzun ise kisalt (rozet karta sigsin)
                genre_text = genre if len(genre) <= 18 else genre[:16] + "…"
                genre_badge = QLabel(genre_text)
                genre_badge.setStyleSheet("""
                    QLabel {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6);
                        color: #ffffff;
                        padding: 4px 10px;
                        border-radius: 10px;
                        font-size: 11px;
                        font-weight: 700;
                    }
                """)
                info_layout.addWidget(genre_badge)

            if year:
                year_badge = QLabel(str(year))
                year_badge.setStyleSheet("""
                    QLabel {
                        background-color: rgba(14, 165, 233, 0.18);
                        color: #7dd3fc;
                        padding: 4px 10px;
                        border-radius: 10px;
                        font-size: 11px;
                        font-weight: 700;
                        border: 1px solid rgba(14, 165, 233, 0.35);
                    }
                """)
                info_layout.addWidget(year_badge)

            info_layout.addStretch()
            card_layout.addLayout(info_layout)
            
            # Yıldız puanlama bölümü - daha belirgin ve ön planda
            rating_layout = QHBoxLayout()
            rating_layout.setSpacing(4)
            rating_layout.setContentsMargins(0, 6, 0, 0)  # Checkbox zaten title_container içinde
            
            if rating:
                try:
                    rating_value = float(rating)
                    # 0-10 arası rating'i 0-5 yıldıza çevir
                    stars_count = min(5, max(0, round(rating_value / 2)))
                    
                    # Yıldızları göster
                    for i in range(5):
                        star_label = QLabel()
                        if i < stars_count:
                            star_label.setText("★")
                            star_label.setStyleSheet("""
                                QLabel {
                                    color: #fbbf24;
                                    font-size: 16px;
                                    font-weight: bold;
                                    padding: 0px;
                                    margin: 0px;
                                }
                            """)
                        else:
                            star_label.setText("☆")
                            star_label.setStyleSheet("""
                                QLabel {
                                    color: #475569;
                                    font-size: 16px;
                                    padding: 0px;
                                    margin: 0px;
                                }
                            """)
                        rating_layout.addWidget(star_label)
                except:
                    pass
            
            rating_layout.addStretch()
            card_layout.addLayout(rating_layout)

            # Yildizlar ile reaksiyon butonlari arasinda esnek bosluk
            # -> reaksiyon butonlari her kartta tam alta sabitlenir
            card_layout.addStretch()

            # ---------------- Begendi / Begenmedi butonlari ----------------
            reaction_layout = QHBoxLayout()
            reaction_layout.setSpacing(8)
            reaction_layout.setContentsMargins(0, 6, 0, 0)

            # Bu kart icin geçerli tepkiyi al
            initial_reaction = current_reactions.get(movie_id)

            like_button = QPushButton()
            like_button.setCursor(Qt.CursorShape.PointingHandCursor)
            like_button.setFixedSize(96, 34)
            like_button.setCheckable(True)
            like_button.setChecked(initial_reaction == "liked")
            like_button.setToolTip("Begendim - benzer filmleri daha cok oner")

            dislike_button = QPushButton()
            dislike_button.setCursor(Qt.CursorShape.PointingHandCursor)
            dislike_button.setFixedSize(96, 34)
            dislike_button.setCheckable(True)
            dislike_button.setChecked(initial_reaction == "disliked")
            dislike_button.setToolTip("Begenmedim - benzer filmleri daha az oner")

            # Buton stilleri - aktif/pasif arasinda CARPICI fark olsun
            like_style_inactive = """
                QPushButton {
                    background-color: rgba(15, 23, 42, 0.5);
                    color: #94a3b8;
                    border: 1px solid #334155;
                    border-radius: 9px;
                    font-size: 15px;
                    font-weight: 600;
                    padding: 2px 4px;
                }
                QPushButton:hover {
                    background-color: rgba(16, 185, 129, 0.18);
                    border: 1px solid #10b981;
                    color: #d1fae5;
                }
                QPushButton:disabled {
                    background-color: rgba(15, 23, 42, 0.25);
                    color: #475569;
                    border: 1px dashed #1e293b;
                }
            """
            like_style_active = """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #047857, stop:0.5 #059669, stop:1 #10b981);
                    color: #ffffff;
                    border: 3px solid #6ee7b7;
                    border-radius: 9px;
                    font-size: 14px;
                    font-weight: 900;
                    padding: 0px 4px;
                    text-align: center;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #065f46, stop:0.5 #047857, stop:1 #059669);
                    border: 3px solid #34d399;
                }
            """
            dislike_style_inactive = """
                QPushButton {
                    background-color: rgba(15, 23, 42, 0.5);
                    color: #94a3b8;
                    border: 1px solid #334155;
                    border-radius: 9px;
                    font-size: 15px;
                    font-weight: 600;
                    padding: 2px 4px;
                }
                QPushButton:hover {
                    background-color: rgba(239, 68, 68, 0.18);
                    border: 1px solid #ef4444;
                    color: #fecaca;
                }
                QPushButton:disabled {
                    background-color: rgba(15, 23, 42, 0.25);
                    color: #475569;
                    border: 1px dashed #1e293b;
                }
            """
            dislike_style_active = """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #991b1b, stop:0.5 #b91c1c, stop:1 #ef4444);
                    color: #ffffff;
                    border: 3px solid #fca5a5;
                    border-radius: 9px;
                    font-size: 14px;
                    font-weight: 900;
                    padding: 0px 4px;
                    text-align: center;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7f1d1d, stop:0.5 #991b1b, stop:1 #dc2626);
                    border: 3px solid #f87171;
                }
            """

            def apply_styles():
                if like_button.isChecked():
                    like_button.setText("✓ Begendim")
                    like_button.setStyleSheet(like_style_active)
                else:
                    like_button.setText("👍")
                    like_button.setStyleSheet(like_style_inactive)

                if dislike_button.isChecked():
                    dislike_button.setText("✓ Begenmedim")
                    dislike_button.setStyleSheet(dislike_style_active)
                else:
                    dislike_button.setText("👎")
                    dislike_button.setStyleSheet(dislike_style_inactive)

            apply_styles()

            # Oylama butonlari yalnizca film "Izledim" olarak secildiyse aktif olur.
            DISABLED_TOOLTIP = "Once filmi sec (sol ust ✓) - oylama icin gereklidir"

            def set_reactions_enabled(enabled,
                                      lb=like_button, db_=dislike_button,
                                      _apply=apply_styles):
                lb.setEnabled(enabled)
                db_.setEnabled(enabled)
                if enabled:
                    lb.setCursor(Qt.CursorShape.PointingHandCursor)
                    db_.setCursor(Qt.CursorShape.PointingHandCursor)
                    lb.setToolTip("Begendim - benzer filmleri daha cok oner")
                    db_.setToolTip("Begenmedim - benzer filmleri daha az oner")
                else:
                    lb.setCursor(Qt.CursorShape.ForbiddenCursor)
                    db_.setCursor(Qt.CursorShape.ForbiddenCursor)
                    lb.setToolTip(DISABLED_TOOLTIP)
                    db_.setToolTip(DISABLED_TOOLTIP)
                _apply()

            def clear_reactions_for_card(mid=movie_id,
                                         lb=like_button, db_=dislike_button,
                                         _apply=apply_styles):
                """Kart icin var olan begeni/begenmeme isaretini hem UI hem DB'den siler."""
                if lb.isChecked():
                    lb.blockSignals(True)
                    lb.setChecked(False)
                    lb.blockSignals(False)
                if db_.isChecked():
                    db_.blockSignals(True)
                    db_.setChecked(False)
                    db_.blockSignals(False)
                self.set_movie_reaction(mid, None)
                _apply()

            # Baslangicta secim yapilmadigi icin oylama devre disi
            set_reactions_enabled(False)

            def on_like_clicked(_=False, mid=movie_id, t=title,
                                lb=like_button, db_=dislike_button, _apply=apply_styles):
                if lb.isChecked():
                    db_.blockSignals(True)
                    db_.setChecked(False)
                    db_.blockSignals(False)
                    ok = self.set_movie_reaction(mid, "liked")
                    if ok:
                        self.statusBar().showMessage(f"'{t}' begenildi - oneriler buna gore guncellenecek")
                    else:
                        lb.blockSignals(True)
                        lb.setChecked(False)
                        lb.blockSignals(False)
                else:
                    self.set_movie_reaction(mid, None)
                    self.statusBar().showMessage(f"'{t}' begeni isareti kaldirildi")
                _apply()

            def on_dislike_clicked(_=False, mid=movie_id, t=title,
                                   lb=like_button, db_=dislike_button, _apply=apply_styles):
                if db_.isChecked():
                    lb.blockSignals(True)
                    lb.setChecked(False)
                    lb.blockSignals(False)
                    ok = self.set_movie_reaction(mid, "disliked")
                    if ok:
                        self.statusBar().showMessage(f"'{t}' begenilmedi olarak isaretlendi")
                    else:
                        db_.blockSignals(True)
                        db_.setChecked(False)
                        db_.blockSignals(False)
                else:
                    self.set_movie_reaction(mid, None)
                    self.statusBar().showMessage(f"'{t}' begenmeme isareti kaldirildi")
                _apply()

            like_button.clicked.connect(on_like_clicked)
            dislike_button.clicked.connect(on_dislike_clicked)

            reaction_layout.addWidget(like_button)
            reaction_layout.addWidget(dislike_button)
            reaction_layout.addStretch()
            card_layout.addLayout(reaction_layout)
            # -----------------------------------------------------------

            # Secim (izledim) toggle'i: SADECE secimi ac/kapa + oylama butonlarini
            # kilitle/ac. Film detayi icin 'i' butonu kullanilir.
            def on_checkbox_changed(
                state,
                movie_id_value=movie_id,
                movie_title=title,
                _apply_select=apply_select_style,
                _set_reactions=set_reactions_enabled,
                _clear_reactions=clear_reactions_for_card
            ):
                _apply_select()
                if state:
                    _set_reactions(True)
                    self.statusBar().showMessage(f"'{movie_title}' secildi")
                else:
                    _clear_reactions()
                    _set_reactions(False)
                    self.statusBar().showMessage(f"'{movie_title}' secimi kaldirildi")

            checkbox.toggled.connect(on_checkbox_changed)

            movie_card.setLayout(card_layout)
            
            # Grid'e ekle
            self.movies_layout.addWidget(movie_card, row, col)
            
            # Sütun ve satır sayacını güncelle
            col += 1
            if col >= columns:
                col = 0
                row += 1
            
            # Checkbox'ı sakla
            self.movie_checkboxes[movie_id] = {
                'checkbox': checkbox,
                'title': title,
                'genre': genre,
                'year': year,
                'rating': rating,
                'description': description,
                'poster_url': poster_url
            }
        self.statusBar().showMessage(f"{len(movies)} film yüklendi - İzlediğiniz filmleri seçin")

    def get_turkish_summary(self, description):
        """Ozeti Turkceye cevir, basarisiz olursa orijinal metni goster."""
        if not isinstance(description, str) or not description.strip():
            return "Bu film icin ozet bilgisi bulunmuyor."

        raw_text = description.strip()
        if raw_text in self.summary_translation_cache:
            return self.summary_translation_cache[raw_text]

        try:
            response = requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={
                    "client": "gtx",
                    "sl": "auto",
                    "tl": "tr",
                    "dt": "t",
                    "q": raw_text
                },
                timeout=8
            )
            if response.status_code == 200:
                payload = response.json()
                translated_text = "".join(part[0] for part in payload[0] if part and part[0]).strip()
                if translated_text:
                    self.summary_translation_cache[raw_text] = translated_text
                    return translated_text
        except Exception:
            pass

        fallback_text = f"Turkce ceviri alinamadi. Orijinal ozet:\n\n{raw_text}"
        self.summary_translation_cache[raw_text] = fallback_text
        return fallback_text

    def get_verified_movie_summary(self, title, year=None, fallback_description=None):
        """Film adini OMDb'de dogrulayip daha dogru ozeti dondur."""
        if not title:
            return fallback_description

        cache_key = (title.strip().lower(), str(year or "").strip())
        if cache_key in self.verified_summary_cache:
            return self.verified_summary_cache[cache_key]

        best_description = fallback_description
        if self.omdb_api_key:
            params = {
                "apikey": self.omdb_api_key,
                "t": title,
                "type": "movie",
                "plot": "full"
            }
            if year:
                params["y"] = year

            try:
                response = requests.get(self.omdb_base_url, params=params, timeout=8)
                response.raise_for_status()
                data = response.json()
                if data.get("Response") == "True":
                    plot = (data.get("Plot") or "").strip()
                    if plot and plot != "N/A":
                        best_description = plot
            except Exception:
                pass

        self.verified_summary_cache[cache_key] = best_description
        return best_description

    def get_or_create_profile_id(self, cursor):
        """Mevcut profil bilgisine gore profile id olustur veya getir."""
        first_name = (self.profile_data.get("first_name", "") or "").strip()
        last_name = (self.profile_data.get("last_name", "") or "").strip()
        age = str(self.profile_data.get("age", "") or "").strip()
        gender = (self.profile_data.get("gender", "Belirtmek istemiyorum") or "Belirtmek istemiyorum").strip()

        profile_key = self.app_user_key or "varsayilan_profil"

        cursor.execute(
            """
            INSERT INTO profiles (profile_key, first_name, last_name, age, gender)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (profile_key)
            DO UPDATE SET
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                age = EXCLUDED.age,
                gender = EXCLUDED.gender
            RETURNING id
            """,
            (profile_key, first_name, last_name, age, gender)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    REACTION_EVENT_TYPES = ("liked", "disliked")
    REACTION_EVENT_SOURCE = "app_card_reaction"

    def set_movie_reaction(self, movie_id, reaction):
        """
        Bir film icin kullanici tepkisini set et.

        reaction: 'liked', 'disliked' veya None (tepkiyi temizler).
        """
        if movie_id is None:
            return False

        if reaction not in (None, "liked", "disliked"):
            raise ValueError(f"Gecersiz reaction: {reaction!r}")

        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            profile_id = self.get_or_create_profile_id(cursor)
            if profile_id is None:
                conn.rollback()
                return False

            # Once mevcut tepkiyi temizle
            cursor.execute(
                """
                DELETE FROM interaction_events
                WHERE profile_id = %s
                  AND movie_id = %s
                  AND event_type IN ('liked', 'disliked')
                  AND event_source = %s
                """,
                (profile_id, movie_id, self.REACTION_EVENT_SOURCE)
            )

            if reaction is not None:
                cursor.execute(
                    """
                    INSERT INTO interaction_events
                        (profile_id, movie_id, event_type, event_value, event_source)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (profile_id, movie_id, event_type, event_source)
                    DO NOTHING
                    """,
                    (
                        profile_id,
                        movie_id,
                        reaction,
                        1.0 if reaction == "liked" else -1.0,
                        self.REACTION_EVENT_SOURCE,
                    )
                )

            conn.commit()
            # Tepki, profil bazli oneriyi etkiler ama modeli yeniden egitmeye
            # gerek yok - recommend() cagrisinda parametre olarak gidiyor.
            return True
        except Exception as exc:
            conn.rollback()
            print(f"[set_movie_reaction] Hata: {exc}")
            return False
        finally:
            self.return_connection(conn)

    def clear_all_reactions_for_current_profile(self):
        """
        Aktif profilin TUM begeni/begenmeme oylarini siler.
        Kural: oylama yalnizca secili (Izledim) film icin gecerli; secim
        oturum bazli oldugundan her yeniden yuklemede oylar temizlenir.
        """
        conn = self.get_connection()
        if not conn:
            return 0

        try:
            cursor = conn.cursor()
            profile_id = self.get_or_create_profile_id(cursor)
            if profile_id is None:
                conn.rollback()
                return 0

            cursor.execute(
                """
                DELETE FROM interaction_events
                WHERE profile_id = %s
                  AND event_type IN ('liked', 'disliked')
                  AND event_source = %s
                """,
                (profile_id, self.REACTION_EVENT_SOURCE),
            )
            deleted = cursor.rowcount or 0
            conn.commit()
            return deleted
        except Exception as exc:
            conn.rollback()
            print(f"[clear_all_reactions_for_current_profile] Hata: {exc}")
            return 0
        finally:
            self.return_connection(conn)

    def get_profile_reactions(self):
        """
        Aktif profilin tepkilerini dondurur: {movie_id: 'liked' | 'disliked'}.
        """
        reactions = {}
        conn = self.get_connection()
        if not conn:
            return reactions

        try:
            cursor = conn.cursor()
            profile_id = self.get_or_create_profile_id(cursor)
            if profile_id is None:
                conn.rollback()
                return reactions

            cursor.execute(
                """
                SELECT movie_id, event_type
                FROM interaction_events
                WHERE profile_id = %s
                  AND event_type IN ('liked', 'disliked')
                  AND event_source = %s
                """,
                (profile_id, self.REACTION_EVENT_SOURCE)
            )
            for movie_id, event_type in cursor.fetchall():
                reactions[movie_id] = event_type
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"[get_profile_reactions] Hata: {exc}")
        finally:
            self.return_connection(conn)

        return reactions

    def save_movie_as_watched(self, movie_id, title):
        """Filmi profile izlendi olarak ekle ve veritabanina yaz."""
        selected_titles = self.profile_data.get("selected_movies", [])
        if not isinstance(selected_titles, list):
            selected_titles = []
        if title and title not in selected_titles:
            selected_titles.append(title)
            self.profile_data["selected_movies"] = selected_titles
            self.save_profile_data()

        if movie_id is None:
            return

        conn = self.get_connection()
        if not conn:
            self.statusBar().showMessage("Profil kaydi yapildi, veritabani baglantisi yok")
            return

        try:
            cursor = conn.cursor()
            profile_id = self.get_or_create_profile_id(cursor)
            if profile_id is None:
                raise ValueError("Profil kaydi olusturulamadi")

            cursor.execute(
                """
                INSERT INTO profile_watched_movies (profile_id, movie_id)
                VALUES (%s, %s)
                ON CONFLICT (profile_id, movie_id) DO NOTHING
                """,
                (profile_id, movie_id)
            )
            self.refresh_recommendation_features(cursor=cursor, rebuild_movie_categories=False)
            self.refresh_ml_training_assets(cursor=cursor)
            conn.commit()
            self.statusBar().showMessage(f"{title} profilde izlendi olarak kaydedildi")
        except Exception as e:
            conn.rollback()
            QMessageBox.warning(self, "Uyari", f"Film veritabanina kaydedilemedi:\n{str(e)}")
        finally:
            self.return_connection(conn)

    def remove_movies_from_profile_records(self, movie_titles):
        """Profildeki secili filmleri hem yerel profil hem veritabanindan cikar."""
        if not movie_titles:
            return

        normalized_titles = {title.strip() for title in movie_titles if isinstance(title, str) and title.strip()}
        if not normalized_titles:
            return

        current_titles = self.profile_data.get("selected_movies", [])
        if not isinstance(current_titles, list):
            current_titles = []
        self.profile_data["selected_movies"] = [title for title in current_titles if title not in normalized_titles]
        self.save_profile_data()

        conn = self.get_connection()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            profile_id = self.get_or_create_profile_id(cursor)
            if profile_id is None:
                raise ValueError("Profil kaydi olusturulamadi")

            cursor.execute(
                """
                DELETE FROM profile_watched_movies pwm
                USING movies m
                WHERE pwm.profile_id = %s
                  AND pwm.movie_id = m.id
                  AND m.title = ANY(%s)
                """,
                (profile_id, list(normalized_titles))
            )
            cursor.execute(
                """
                DELETE FROM interaction_events ie
                USING movies m
                WHERE ie.profile_id = %s
                  AND ie.movie_id = m.id
                  AND m.title = ANY(%s)
                """,
                (profile_id, list(normalized_titles))
            )
            self.refresh_recommendation_features(cursor=cursor, rebuild_movie_categories=False)
            self.refresh_ml_training_assets(cursor=cursor)
            conn.commit()
        except Exception as e:
            conn.rollback()
            QMessageBox.warning(self, "Uyari", f"Secili filmler veritabanindan cikarilamadi:\n{str(e)}")
        finally:
            self.return_connection(conn)

    def delete_movies_from_database(self, movie_titles):
        """Filmleri veritabanindan tamamen sil (onerilerden kaldirma icin)."""
        normalized_titles = [title.strip() for title in movie_titles if isinstance(title, str) and title.strip()]
        if not normalized_titles:
            return 0

        # Once profildeki secili listeden cikar
        self.remove_movies_from_profile_records(normalized_titles)

        conn = self.get_connection()
        if not conn:
            return 0

        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM movies WHERE title = ANY(%s)",
                (normalized_titles,)
            )
            deleted_count = cursor.rowcount
            self.refresh_recommendation_features(cursor=cursor, rebuild_movie_categories=True)
            self.refresh_ml_training_assets(cursor=cursor)
            conn.commit()
            if deleted_count > 0:
                self.mark_content_recommender_dirty()
            return deleted_count
        except Exception as e:
            conn.rollback()
            QMessageBox.warning(self, "Uyari", f"Filmler veritabanindan silinemedi:\n{str(e)}")
            return 0
        finally:
            self.return_connection(conn)

    def show_movie_info_dialog(self, movie_id=None, title=None, genre=None, year=None, rating=None, description=None):
        """Film kartindaki 'i' Detay butonuyla acilir: salt-bilgi gosterici (secimi etkilemez)."""
        if not title:
            return False

        meta_parts = []
        if genre:
            meta_parts.append(f"Tur: {genre}")
        if year:
            meta_parts.append(f"Yil: {year}")
        if rating:
            meta_parts.append(f"Puan: {rating}/10")
        if not meta_parts:
            meta_parts.append("Ek bilgi bulunmuyor")

        meta_text = " | ".join(meta_parts)
        verified_summary = self.get_verified_movie_summary(title=title, year=year, fallback_description=description)
        summary_text = self.get_turkish_summary(verified_summary)

        dialog = QDialog(self)
        dialog.setWindowTitle("Film Detayi")
        dialog.setMinimumWidth(620)
        dialog.setMinimumHeight(440)
        dialog.setStyleSheet("QDialog { background-color: #0f1419; }")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: 700;")
        layout.addWidget(title_label)

        meta_label = QLabel(meta_text)
        meta_label.setWordWrap(True)
        meta_label.setStyleSheet("color: #94a3b8; font-size: 13px;")
        layout.addWidget(meta_label)

        summary_label = QLabel("Ozet")
        summary_label.setStyleSheet("color: #3b82f6; font-size: 14px; font-weight: 700; padding-top: 4px;")
        layout.addWidget(summary_label)

        summary_textbox = QTextEdit()
        summary_textbox.setReadOnly(True)
        summary_textbox.setPlainText(summary_text)
        summary_textbox.setStyleSheet("""
            QTextEdit {
                background-color: #111827;
                border: 1px solid #334155;
                border-radius: 8px;
                color: #e2e8f0;
                padding: 10px;
                font-size: 13px;
            }
        """)
        layout.addWidget(summary_textbox, 1)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addStretch()

        close_button = QPushButton("Kapat")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6);
                color: #ffffff;
                padding: 8px 22px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                border: none;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #2563eb);
            }
        """)
        close_button.clicked.connect(dialog.accept)
        button_row.addWidget(close_button)

        layout.addLayout(button_row)

        dialog.exec()
        return True

    def load_profile_data(self):
        """Profil verisini dosyadan yükle."""
        if not os.path.exists(self.profile_file):
            self.save_profile_data()
            return

        try:
            with open(self.profile_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.profile_data.update({
                    "first_name": data.get("first_name", ""),
                    "last_name": data.get("last_name", ""),
                    "age": data.get("age", ""),
                    "gender": data.get("gender", "Belirtmek istemiyorum"),
                    "selected_movies": data.get("selected_movies", [])
                })
                if not isinstance(self.profile_data.get("selected_movies"), list):
                    self.profile_data["selected_movies"] = []
        except Exception as e:
            print(f"Profil verisi yuklenemedi: {e}")

    def save_profile_data(self):
        """Profil verisini dosyaya kaydet."""
        try:
            self.profile_data["profile_user_key"] = self.app_user_key
            with open(self.profile_file, "w", encoding="utf-8") as f:
                json.dump(self.profile_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "Uyarı", f"Profil kaydedilemedi:\n{str(e)}")

    def get_current_selected_movies(self):
        """Arayuzde secili filmleri liste olarak dondur."""
        selected = []
        for movie_id, movie_data in self.movie_checkboxes.items():
            if movie_data['checkbox'].isChecked():
                selected.append({
                    'id': movie_id,
                    'title': movie_data['title'],
                    'genre': movie_data['genre'],
                    'year': movie_data['year'],
                    'rating': movie_data['rating']
                })
        return selected

    def show_profile_dialog(self):
        """Sol ustteki profil ikonundan acilan profil dialogu."""
        selected_movies = self.get_current_selected_movies()
        checked_titles = [movie['title'] for movie in selected_movies]
        stored_titles = self.profile_data.get("selected_movies", [])
        if not isinstance(stored_titles, list):
            stored_titles = []
        selected_titles = list(dict.fromkeys(stored_titles + checked_titles))

        dialog = QDialog(self)
        dialog.setWindowTitle("Kullanici Profili")
        dialog.setMinimumWidth(480)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #1a1f2e;
                color: #e2e8f0;
            }
            QLabel {
                color: #e2e8f0;
            }
        """)

        layout = QVBoxLayout()
        form_layout = QFormLayout()

        active_user_label = QLabel(f"Aktif profil: {self.app_user_key}")
        active_user_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(active_user_label)

        first_name_input = QLineEdit(self.profile_data.get("first_name", ""))
        first_name_input.setPlaceholderText("Ad")

        last_name_input = QLineEdit(self.profile_data.get("last_name", ""))
        last_name_input.setPlaceholderText("Soyad")

        age_input = QLineEdit(str(self.profile_data.get("age", "")))
        age_input.setPlaceholderText("Yas")

        gender_combo = QComboBox()
        gender_options = ["Kadin", "Erkek", "Diger", "Belirtmek istemiyorum"]
        gender_combo.addItems(gender_options)
        saved_gender = self.profile_data.get("gender", "Belirtmek istemiyorum")
        if saved_gender in gender_options:
            gender_combo.setCurrentText(saved_gender)

        for widget in [first_name_input, last_name_input, age_input, gender_combo]:
            widget.setStyleSheet("""
                QLineEdit, QComboBox {
                    background-color: #0f1419;
                    color: #e2e8f0;
                    border: 2px solid #2d3748;
                    border-radius: 8px;
                    padding: 8px;
                    font-size: 13px;
                }
                QLineEdit:focus, QComboBox:focus {
                    border: 2px solid #3b82f6;
                }
                QLineEdit::placeholder {
                    color: #94a3b8;
                }
                QComboBox QAbstractItemView {
                    background-color: #1a1f2e;
                    color: #e2e8f0;
                    border: 1px solid #334155;
                    selection-background-color: #2563eb;
                    selection-color: #ffffff;
                }
            """)

        form_layout.addRow("Ad:", first_name_input)
        form_layout.addRow("Soyad:", last_name_input)
        form_layout.addRow("Yas:", age_input)
        form_layout.addRow("Cinsiyet:", gender_combo)
        layout.addLayout(form_layout)

        selected_label = QLabel("Secilen Filmler (Profilde saklanir):")
        selected_label.setStyleSheet("color: #cbd5e1; font-weight: 600; margin-top: 8px;")
        layout.addWidget(selected_label)

        movies_list_widget = QListWidget()
        movies_list_widget.addItems(selected_titles)
        movies_list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        movies_list_widget.setMinimumHeight(150)
        movies_list_widget.setStyleSheet("""
            QListWidget {
                background-color: #0f1419;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 10px;
                color: #94a3b8;
            }
            QListWidget::item:selected {
                background-color: #1d4ed8;
                color: #ffffff;
                border-radius: 5px;
            }
        """)
        layout.addWidget(movies_list_widget)

        removed_titles = set()

        remove_selected_button = QPushButton("✖ Secili Filmi Sil")
        remove_selected_button.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_selected_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #dc2626, stop:1 #ef4444);
                color: #ffffff;
                padding: 8px 14px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                border: none;
                max-width: 180px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b91c1c, stop:1 #dc2626);
            }
        """)

        def remove_selected_titles_from_profile():
            items = movies_list_widget.selectedItems()
            if not items:
                QMessageBox.information(dialog, "Bilgi", "Lutfen silmek icin bir film secin.")
                return

            for item in items:
                title = item.text().strip()
                if not title:
                    continue
                removed_titles.add(title)
                row = movies_list_widget.row(item)
                movies_list_widget.takeItem(row)

                for movie_data in self.movie_checkboxes.values():
                    if movie_data.get("title") == title:
                        movie_data["checkbox"].setChecked(False)
                        break

        remove_selected_button.clicked.connect(remove_selected_titles_from_profile)
        layout.addWidget(remove_selected_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        buttons.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6);
                color: #ffffff;
                padding: 8px 20px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #2563eb);
            }
        """)
        layout.addWidget(buttons)
        dialog.setLayout(layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            age_text = age_input.text().strip()
            if age_text and not age_text.isdigit():
                QMessageBox.warning(self, "Uyarı", "Yas alani sadece sayi olmali.")
                return

            self.profile_data["first_name"] = first_name_input.text().strip()
            self.profile_data["last_name"] = last_name_input.text().strip()
            self.profile_data["age"] = age_text
            self.profile_data["gender"] = gender_combo.currentText()
            updated_titles = [movies_list_widget.item(i).text().strip() for i in range(movies_list_widget.count())]
            self.profile_data["selected_movies"] = [title for title in updated_titles if title]
            self.save_profile_data()
            self.remove_movies_from_profile_records(list(removed_titles))
            self.statusBar().showMessage("Profil bilgileri kaydedildi")
            QMessageBox.information(self, "Basarili", "Profil bilgileri kaydedildi.")
    
    def save_selected_movies(self):
        """Seçilen filmleri kaydet"""
        selected = self.get_current_selected_movies()
        
        if not selected:
            QMessageBox.information(self, "Bilgi", "Lütfen en az bir film seçin!")
            return

        self.selected_movies = selected
        self.profile_data["selected_movies"] = [movie["title"] for movie in selected]
        self.save_profile_data()

        # Veritabanina/profile watched tablosuna kayit sadece bu butondan yapilsin
        conn = self.get_connection()
        if conn:
            try:
                cursor = conn.cursor()
                profile_id = self.get_or_create_profile_id(cursor)
                if profile_id is None:
                    raise ValueError("Profil kaydi olusturulamadi")

                inserted_count = 0
                for movie in selected:
                    movie_id = movie.get("id")
                    if not movie_id:
                        continue
                    cursor.execute(
                        """
                        INSERT INTO profile_watched_movies (profile_id, movie_id)
                        VALUES (%s, %s)
                        ON CONFLICT (profile_id, movie_id) DO NOTHING
                        """,
                        (profile_id, movie_id)
                    )
                    if cursor.rowcount > 0:
                        inserted_count += 1

                self.refresh_recommendation_features(cursor=cursor, rebuild_movie_categories=False)
                self.refresh_ml_training_assets(cursor=cursor)
                conn.commit()
                self.statusBar().showMessage(f"{len(selected)} film kaydedildi ({inserted_count} yeni profil kaydi)")
            except Exception as e:
                conn.rollback()
                QMessageBox.warning(self, "Uyari", f"Profil-film kayitlari veritabanina yazilamadi:\n{str(e)}")
            finally:
                self.return_connection(conn)
        
        # Secilen filmleri kullaniciya ozel dosyaya kaydet (AI icin veri)
        try:
            selected_movies_file = f"selected_movies_{self.app_user_key}.txt"
            with open(selected_movies_file, "a", encoding="utf-8") as f:
                for movie in selected:
                    f.write(f"{movie['title']}|{movie.get('genre', 'N/A')}|{movie.get('year', 'N/A')}|{movie.get('rating', 'N/A')}\n")
            
            QMessageBox.information(
                self, 
                "Başarılı", 
                f"{len(selected)} film başarıyla kaydedildi!\n\nSecilen filmler '{selected_movies_file}' dosyasina kaydedildi."
            )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Filmler kaydedilirken bir hata oluştu:\n{str(e)}")
    
    def load_categories_from_db(self):
        """Veritabanından tüm benzersiz kategorileri yükle"""
        categories = ["Tümü"]  # Her zaman "Tümü" seçeneği olsun
        
        conn = self.get_connection()
        if not conn:
            return categories
        
        try:
            cursor = conn.cursor()
            # Oneri tablosundan normalize edilmis kategorileri al
            cursor.execute("""
                SELECT DISTINCT category
                FROM movie_categories
                WHERE category IS NOT NULL
                  AND TRIM(category) != ''
                ORDER BY category
            """)
            
            genres = cursor.fetchall()
            
            for (category,) in genres:
                if category:
                    clean_category = category.strip()
                    if clean_category and clean_category not in categories:
                        categories.append(clean_category)
            
        except Exception as e:
            print(f"Kategoriler yuklenirken hata: {str(e)}")
        finally:
            self.return_connection(conn)
        
        # Eğer hiç kategori yoksa varsayılan kategorileri ekle
        if len(categories) == 1:  # Sadece "Tümü" varsa
            categories.extend(["Action", "Drama", "Comedy", "Sci-Fi", "Horror", "Thriller"])
        
        return categories
    
    def on_category_changed(self, category):
        self.update_popular_movies(category)
    
    def get_movies_by_category(self, category):
        """Kategoriye göre filmleri getir (normalize kategori tablosu ile)."""
        conn = self.get_connection()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            
            if category == "Tümü":
                cursor.execute('SELECT id, title, genre, year, rating, description, poster_url FROM movies ORDER BY rating DESC NULLS LAST, year DESC NULLS LAST LIMIT 20')
            else:
                cursor.execute("""
                    SELECT DISTINCT m.id, m.title, m.genre, m.year, m.rating, m.description, m.poster_url
                    FROM movies m
                    JOIN movie_categories mc ON mc.movie_id = m.id
                    WHERE mc.category ILIKE %s
                    ORDER BY rating DESC NULLS LAST, year DESC NULLS LAST 
                    LIMIT 20
                """, (category,))
            
            movies = cursor.fetchall()
            return movies
        except Exception as e:
            QMessageBox.critical(self, "Veritabanı Hatası", 
                                f"Filmler getirilirken hata oluştu:\n{str(e)}")
            return []
        finally:
            self.return_connection(conn)
    
    def update_popular_movies(self, category):
        """Kategoriye göre filmleri göster"""
        try:
            while self.popular_layout.count():
                item = self.popular_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        except:
            pass
        
        movies = self.get_movies_by_category(category)
        
        if not movies:
            empty_label = QLabel(f"{category} kategorisinde\nfilm bulunamadı")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #64748b; font-size: 12px; padding: 30px 20px; line-height: 1.6; background-color: #0f1419; border-radius: 12px; border: 2px dashed #2d3748;")
            empty_label.setWordWrap(True)
            self.popular_layout.addWidget(empty_label)
            self.popular_layout.addStretch()
            return
        
        for movie_data in movies:
            movie_id = movie_data[0]
            title = movie_data[1]
            genre = movie_data[2] if len(movie_data) > 2 else None
            year = movie_data[3] if len(movie_data) > 3 else None
            rating = movie_data[4] if len(movie_data) > 4 else None
            description = movie_data[5] if len(movie_data) > 5 else None
            poster_url = movie_data[6] if len(movie_data) > 6 else None
            
            movie_item = QFrame()
            movie_item.setFixedHeight(140)  # Poster için daha yüksek
            movie_item.setStyleSheet("""
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #18233b, stop:1 #101827);
                    border: 2px solid #304267;
                    border-radius: 10px;
                    padding: 10px;
                    margin: 3px 0px;
                }
                QFrame:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #223153, stop:1 #18233b);
                    border: 2px solid #60a5fa;
                }
            """)
            
            item_main_layout = QHBoxLayout()
            item_main_layout.setSpacing(10)
            item_main_layout.setContentsMargins(0, 0, 0, 0)
            
            # Küçük poster (sol tarafta)
            # Poster URL validasyonu: boş, None, "N/A" veya geçersiz URL kontrolü
            is_valid_poster_url_small = (poster_url and 
                                        poster_url.strip() != '' and 
                                        poster_url.strip().upper() != 'N/A' and
                                        (poster_url.startswith('http://') or poster_url.startswith('https://')))
            
            if is_valid_poster_url_small:
                poster_label = QLabel()
                poster_label.setFixedSize(50, 70)
                poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                poster_label.setStyleSheet("""
                    QLabel {
                        background-color: #0f1419;
                        border: 1px solid #2d3748;
                        border-radius: 6px;
                    }
                """)
                poster_label.setScaledContents(False)
                
                # Poster'i arka planda yükle (performans için) - retry mekanizması ile
                def load_poster_async_small(url, label):
                    max_retries = 2
                    for attempt in range(max_retries):
                        try:
                            response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'}, stream=True)
                            if response.status_code == 200:
                                # Content-Type kontrolü
                                content_type = response.headers.get('Content-Type', '')
                                if 'image' not in content_type:
                                    if attempt < max_retries - 1:
                                        time.sleep(0.5)
                                        continue
                                    break
                                
                                pixmap = QPixmap()
                                pixmap.loadFromData(response.content)
                                if not pixmap.isNull():
                                    scaled_pixmap = pixmap.scaled(50, 70, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                                    # Thread-safe UI güncellemesi
                                    QMetaObject.invokeMethod(label, "setPixmap", Qt.ConnectionType.QueuedConnection, Q_ARG(QPixmap, scaled_pixmap))
                                    QMetaObject.invokeMethod(label, "setStyleSheet", Qt.ConnectionType.QueuedConnection,
                                        Q_ARG(str, """
                                            QLabel {
                                                background-color: transparent;
                                                border: 1px solid #2d3748;
                                                border-radius: 6px;
                                            }
                                        """))
                                    return  # Başarılı, çık
                                else:
                                    if attempt < max_retries - 1:
                                        time.sleep(0.5)
                                        continue
                        except requests.exceptions.Timeout:
                            if attempt < max_retries - 1:
                                time.sleep(1)
                                continue
                        except requests.exceptions.RequestException:
                            if attempt < max_retries - 1:
                                time.sleep(0.5)
                                continue
                        except Exception:
                            if attempt < max_retries - 1:
                                time.sleep(0.5)
                                continue
                        break  # Tüm denemeler başarısız
                
                Thread(target=load_poster_async_small, args=(poster_url, poster_label), daemon=True).start()
                
                item_main_layout.addWidget(poster_label)
            
            # Sağ tarafta bilgiler
            item_layout = QVBoxLayout()
            item_layout.setSpacing(5)
            item_layout.setContentsMargins(0, 0, 0, 0)
            
            # Film başlığı
            title_label = QLabel(title)
            title_label.setWordWrap(True)
            title_label.setMaximumHeight(35)
            title_label.setStyleSheet("""
                QLabel {
                    color: #ffffff;
                    font-size: 12px;
                    font-weight: 700;
                    padding: 2px 0px;
                }
            """)
            title_font = QFont("Segoe UI", 12, QFont.Weight.Bold)
            title_label.setFont(title_font)
            item_layout.addWidget(title_label)
            
            # Film bilgileri
            info_layout = QHBoxLayout()
            info_layout.setSpacing(5)
            
            if genre:
                genre_badge = QLabel(f"🎬 {genre}")
                genre_badge.setStyleSheet("""
                    QLabel {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6);
                        color: #ffffff;
                        padding: 2px 6px;
                        border-radius: 10px;
                        font-size: 8px;
                        font-weight: 600;
                    }
                """)
                info_layout.addWidget(genre_badge)
            
            if year:
                year_badge = QLabel(f"📅 {year}")
                year_badge.setStyleSheet("""
                    QLabel {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0ea5e9, stop:1 #38bdf8);
                        color: #ffffff;
                        padding: 2px 6px;
                        border-radius: 10px;
                        font-size: 8px;
                        font-weight: 600;
                    }
                """)
                info_layout.addWidget(year_badge)
            
            info_layout.addStretch()
            item_layout.addLayout(info_layout)
            
            # Yıldız puanlama - belirgin yıldızlar
            if rating:
                try:
                    rating_value = float(rating)
                    stars_count = min(5, max(0, round(rating_value / 2)))
                    
                    stars_layout = QHBoxLayout()
                    stars_layout.setSpacing(3)
                    stars_layout.setContentsMargins(0, 4, 0, 0)
                    
                    for i in range(5):
                        star_label = QLabel()
                        if i < stars_count:
                            star_label.setText("★")
                            star_label.setStyleSheet("""
                                QLabel {
                                    color: #fbbf24;
                                    font-size: 14px;
                                    font-weight: bold;
                                    padding: 0px;
                                    margin: 0px;
                                }
                            """)
                        else:
                            star_label.setText("☆")
                            star_label.setStyleSheet("""
                                QLabel {
                                    color: #475569;
                                    font-size: 14px;
                                    padding: 0px;
                                    margin: 0px;
                                }
                            """)
                        stars_layout.addWidget(star_label)
                    
                    rating_text = QLabel(f"({rating}/10)")
                    rating_text.setStyleSheet("""
                        QLabel {
                            color: #fbbf24;
                            font-size: 10px;
                            font-weight: 600;
                            margin-left: 5px;
                            padding: 0px;
                        }
                    """)
                    stars_layout.addWidget(rating_text)
                    stars_layout.addStretch()
                    
                    item_layout.addLayout(stars_layout)
                except:
                    pass
            
            item_main_layout.addLayout(item_layout)
            movie_item.setLayout(item_main_layout)
            self.popular_layout.addWidget(movie_item)
        
        self.popular_layout.addStretch()

    def get_profile_based_recommendations(self, min_count=1, max_count=5):
        """
        Egitilmis icerik tabanli ML modeli ile profil filmlerine benzer top-N filmi dondurur.

        Donus: liste of (movie_id, title, year, rating, genre, actors, score)
        """
        conn = self.get_connection()
        if not conn:
            return []

        try:
            cursor = conn.cursor()

            profile_id = self.get_or_create_profile_id(cursor)

            # KURAL: Sadece SU AN UI'da ✓ ile secili olan filmler baz alinir.
            # Gecmis kayitlar (profil JSON'undaki selected_movies, DB'deki
            # profile_watched_movies tablosu) bilerek yoksayilir - uygulama
            # her acildiginda kullanici secimlerine yeniden baslar.
            watched_ids = {
                movie["id"]
                for movie in self.get_current_selected_movies()
                if movie.get("id") is not None
            }

            # Begenilen / Begenilmeyen filmleri al
            # Reaksiyonlar zaten load_random_movies basinda her oturumda
            # temizleniyor -> sadece bu oturumdaki begenmeler/begenmemeler gelir.
            liked_ids = set()
            disliked_ids = set()
            if profile_id is not None:
                cursor.execute(
                    """
                    SELECT movie_id, event_type
                    FROM interaction_events
                    WHERE profile_id = %s
                      AND event_type IN ('liked', 'disliked')
                      AND event_source = %s
                    """,
                    (profile_id, self.REACTION_EVENT_SOURCE)
                )
                for movie_id, event_type in cursor.fetchall():
                    if event_type == "liked":
                        liked_ids.add(movie_id)
                    elif event_type == "disliked":
                        disliked_ids.add(movie_id)

            conn.commit()

            recommender = self.get_content_recommender()
            if recommender is None:
                return []

            # KURAL: Profilde pozitif sinyal (secili veya begenilen film) yoksa
            # oneri vermeyiz. Cold-start fallback yok - kullanici once secim yapmali.
            has_positive_signal = bool(watched_ids or liked_ids)
            if not has_positive_signal:
                return []

            # Profil filmlerine en benzer top-N oneriyi al
            # Begenilen filmler izlenenlerden 3 kat daha guclu sinyal verir;
            # begenilmeyenler de simetrik olarak (dislike_weight=1.0) cezalandirilir.
            ml_results = recommender.recommend(
                watched_ids=list(watched_ids),
                liked_ids=list(liked_ids),
                disliked_ids=list(disliked_ids),
                top_k=max_count,
                exclude_watched=True,
                like_boost=3.0,
                dislike_weight=1.0,
            )

            # Model bir sey dondurmediyse de bos liste dondur (fallback yok)
            if not ml_results:
                return []

            # Onerilen movie_id'ler icin DB'den meta-veriyi tek seferde cek
            ml_ids = [r["movie_id"] for r in ml_results]
            cursor.execute(
                """
                SELECT id, title, year, rating, genre, COALESCE(actors, '')
                FROM movies
                WHERE id = ANY(%s)
                """,
                (ml_ids,)
            )
            meta_by_id = {row[0]: row for row in cursor.fetchall()}

            results = []
            for r in ml_results:
                mid = r["movie_id"]
                meta = meta_by_id.get(mid)
                if meta is None:
                    continue
                _, title, year, rating, genre, actors = meta
                results.append((mid, title, year, rating, genre, actors, float(r["score"])))

            if results and len(results) < min_count:
                # Cok az sonuc varsa rating'e gore tamamla
                excluded_ids = watched_ids | liked_ids | disliked_ids
                existing_ids = {r[0] for r in results}.union(excluded_ids)
                cursor.execute(
                    """
                    SELECT id, title, year, rating, genre, COALESCE(actors, '')
                    FROM movies
                    WHERE id != ALL(%s)
                    ORDER BY rating DESC NULLS LAST, year DESC NULLS LAST
                    LIMIT %s
                    """,
                    (list(existing_ids) if existing_ids else [-1], min_count - len(results))
                )
                for row in cursor.fetchall():
                    results.append((*row, 0.0))

            return results[:max_count]
        except Exception as e:
            conn.rollback()
            QMessageBox.warning(self, "Uyari", f"Oneri hesaplanirken hata olustu:\n{str(e)}")
            return []
        finally:
            self.return_connection(conn)

    def show_recommendation_dialog(self):
        """Ust menudeki butondan acilan film oneri penceresi (ML icerik tabanli)."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Sana Ozel Film Onerileri (AI)")
        dialog.setMinimumWidth(780)
        dialog.setMinimumHeight(560)
        dialog.setStyleSheet("QDialog { background-color: #0f1419; }")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title_label = QLabel("🍿 Profiline Gore Film Onerileri")
        title_label.setStyleSheet("color: #60a5fa; font-size: 20px; font-weight: 700;")
        layout.addWidget(title_label)

        info_label = QLabel("Profilindeki filmlere icerik (tur, oyuncu, aciklama, puan, yil) benzerligine gore en yakin filmler.")
        info_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Ust kontrol satiri: top-K + yeniden egit butonu
        control_row = QHBoxLayout()
        control_row.setSpacing(10)

        control_row.addWidget(QLabel("<span style='color:#cbd5e1;font-size:12px;'>Oneri sayisi:</span>"))

        top_k_combo = QComboBox()
        top_k_combo.addItems(["5", "10", "15", "20"])
        top_k_combo.setCurrentText("5")
        top_k_combo.setFixedWidth(70)
        top_k_combo.setStyleSheet("""
            QComboBox {
                background-color: #1f2937;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #1f2937;
                color: #e2e8f0;
                selection-background-color: #1d4ed8;
            }
        """)
        control_row.addWidget(top_k_combo)
        control_row.addStretch()
        layout.addLayout(control_row)

        recommendation_list = QListWidget()
        recommendation_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        recommendation_list.setToolTip(
            "Birden fazla film secmek icin Ctrl ile tikla veya Shift ile arali sec."
        )
        recommendation_list.setStyleSheet("""
            QListWidget {
                background-color: #111827;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 8px;
                color: #e2e8f0;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 10px 8px;
                border-bottom: 1px solid rgba(51, 65, 85, 0.45);
            }
            QListWidget::item:selected {
                background-color: #1d4ed8;
                color: #ffffff;
            }
        """)
        layout.addWidget(recommendation_list, 1)

        model_info_label = QLabel("")
        model_info_label.setStyleSheet("color: #64748b; font-size: 11px;")
        model_info_label.setWordWrap(True)
        layout.addWidget(model_info_label)

        def refresh_list():
            try:
                top_k = int(top_k_combo.currentText())
            except ValueError:
                top_k = 5

            recommendation_list.clear()
            recommendations = self.get_profile_based_recommendations(min_count=1, max_count=top_k)

            if not recommendations:
                placeholder = QListWidgetItem(
                    "Henuz film secmediniz.\n\n"
                    "Oneri alabilmek icin once kart uzerindeki ✓ butonuyla\n"
                    "izlediginiz/begendiginiz filmleri secin, sonra tekrar deneyin."
                )
                placeholder.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                recommendation_list.addItem(placeholder)
                self.statusBar().showMessage("Profilde secili film yok - once film secin")
                return

            for index, item in enumerate(recommendations, start=1):
                movie_id, title, year, rating, genre, actors, score = item
                year_text = str(year) if year else "Yil yok"
                rating_text = f"{rating:.1f}/10" if rating is not None else "Puan yok"
                genre_text = genre or "Tur yok"
                # Oyuncu metnini kisalt
                actors_text = actors if actors else "Oyuncu bilgisi yok"
                if len(actors_text) > 60:
                    actors_text = actors_text[:57] + "..."
                score_text = f"%{score * 100:.0f}" if score > 0 else "puan tabanli"

                item_text = (
                    f"{index}. {title} ({year_text})\n"
                    f"   Benzerlik: {score_text}  |  IMDb: {rating_text}  |  Tur: {genre_text}\n"
                    f"   Oyuncular: {actors_text}"
                )
                list_item = QListWidgetItem(item_text)
                list_item.setData(Qt.ItemDataRole.UserRole, title)
                recommendation_list.addItem(list_item)

            self.statusBar().showMessage(f"{len(recommendations)} film onerildi")

            # Model meta bilgisi
            rec_model = self._content_recommender
            if rec_model and rec_model.stats:
                s = rec_model.stats
                model_info_label.setText(
                    f"Model: {s.movie_count} film, {s.feature_dim} ozellik  "
                    f"(kategori×{rec_model.weights.category}, oyuncu×{rec_model.weights.actor}, "
                    f"aciklama×{rec_model.weights.description}, rating×{rec_model.weights.rating}, "
                    f"yil×{rec_model.weights.year})"
                )

        top_k_combo.currentTextChanged.connect(lambda _: refresh_list())

        refresh_list()

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        select_all_button = QPushButton("✓ Tumunu Sec")
        select_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        select_all_button.setStyleSheet("""
            QPushButton {
                background-color: #1f2937;
                color: #e2e8f0;
                padding: 8px 14px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
                border: 1px solid #334155;
            }
            QPushButton:hover {
                background-color: #334155;
                border: 1px solid #60a5fa;
            }
        """)
        select_all_button.clicked.connect(recommendation_list.selectAll)
        action_row.addWidget(select_all_button)

        clear_selection_button = QPushButton("⨯ Secimi Temizle")
        clear_selection_button.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_selection_button.setStyleSheet(select_all_button.styleSheet())
        clear_selection_button.clicked.connect(recommendation_list.clearSelection)
        action_row.addWidget(clear_selection_button)

        delete_recommendation_button = QPushButton("🗑 Secili Onerileri Sil")
        delete_recommendation_button.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_recommendation_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #dc2626, stop:1 #ef4444);
                color: #ffffff;
                padding: 8px 14px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b91c1c, stop:1 #dc2626);
            }
        """)

        def delete_selected_recommendation():
            selected_items = recommendation_list.selectedItems()
            if not selected_items:
                QMessageBox.information(
                    dialog,
                    "Bilgi",
                    "Lutfen silmek icin en az bir oneri secin.\n"
                    "(Birden fazla secmek icin Ctrl veya Shift ile tiklayin.)"
                )
                return

            titles_to_delete = []
            for item in selected_items:
                title = item.data(Qt.ItemDataRole.UserRole)
                if title:
                    titles_to_delete.append(title)

            if not titles_to_delete:
                QMessageBox.information(dialog, "Bilgi", "Secili satirlar silinebilecek film icermiyor.")
                return

            if len(titles_to_delete) == 1:
                confirm_text = f"'{titles_to_delete[0]}' veritabanindan tamamen silinsin mi?"
            else:
                preview = "\n  - ".join(titles_to_delete[:5])
                extra = f"\n  ... ve {len(titles_to_delete) - 5} film daha" if len(titles_to_delete) > 5 else ""
                confirm_text = (
                    f"Asagidaki {len(titles_to_delete)} film veritabanindan tamamen silinsin mi?\n\n"
                    f"  - {preview}{extra}"
                )

            confirm = QMessageBox.question(
                dialog,
                "Toplu Silme Onayi",
                confirm_text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

            deleted_count = self.delete_movies_from_database(titles_to_delete)
            if deleted_count > 0:
                # Silinen filmlerin item'larini listeden cikar
                for item in selected_items:
                    title = item.data(Qt.ItemDataRole.UserRole)
                    if title in titles_to_delete:
                        row = recommendation_list.row(item)
                        if row >= 0:
                            recommendation_list.takeItem(row)

                self.load_random_movies()
                self.update_popular_movies(self.category_combo.currentText())
                self.mark_content_recommender_dirty()

                if deleted_count == len(titles_to_delete):
                    self.statusBar().showMessage(f"{deleted_count} film veritabanindan silindi")
                else:
                    self.statusBar().showMessage(
                        f"{deleted_count}/{len(titles_to_delete)} film silindi"
                    )
            else:
                QMessageBox.warning(dialog, "Uyari", "Filmler silinemedi veya zaten mevcut degildi.")

        delete_recommendation_button.clicked.connect(delete_selected_recommendation)
        action_row.addWidget(delete_recommendation_button)
        action_row.addStretch()
        layout.addLayout(action_row)

        close_button = QPushButton("Kapat")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6);
                color: #ffffff;
                padding: 8px 18px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                border: none;
                min-width: 100px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #2563eb);
            }
        """)
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)

        dialog.exec()

    def ensure_omdb_api_key(self):
        """API key yoksa kullanicidan iste."""
        if self.omdb_api_key:
            return True

        dialog = QDialog(self)
        dialog.setWindowTitle("OMDb API Key")
        dialog.setStyleSheet("QDialog { background-color: #1a1f2e; }")
        layout = QFormLayout()

        api_key_input = QLineEdit()
        api_key_input.setPlaceholderText("OMDb API Key girin...")
        api_key_input.setStyleSheet("""
            QLineEdit {
                background-color: #0f1419;
                color: #e2e8f0;
                border: 2px solid #2d3748;
                border-radius: 8px;
                padding: 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid #3b82f6;
            }
        """)

        info_label = QLabel("OMDb API Key almak icin:\nhttps://www.omdbapi.com/apikey.aspx")
        info_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        info_label.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        layout.addRow("API Key:", api_key_input)
        layout.addRow(info_label)
        layout.addRow(buttons)
        dialog.setLayout(layout)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        self.omdb_api_key = api_key_input.text().strip()
        if not self.omdb_api_key:
            QMessageBox.warning(self, "Uyari", "API Key bos olamaz.")
            return False
        return True

    def find_missing_posters(self):
        """Veritabanindaki eksik/gecersiz afis baglantilarini listele."""
        conn = self.get_connection()
        if not conn:
            QMessageBox.critical(self, "Hata", "Veritabani baglantisi kurulamadigi icin afis kontrolu yapilamadi.")
            return

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, poster_url FROM movies ORDER BY id")
            rows = cursor.fetchall()

            missing_entries = []
            invalid_entries = []
            for movie_id, title, poster_url in rows:
                url = (poster_url or "").strip()
                if not url or url.upper() == "N/A":
                    missing_entries.append((movie_id, title))
                elif not (url.startswith("http://") or url.startswith("https://")):
                    invalid_entries.append((movie_id, title, url))

            total_missing = len(missing_entries) + len(invalid_entries)
            if total_missing == 0:
                QMessageBox.information(self, "Afiş Kontrolü", "Tum filmlerde afis baglantisi mevcut gorunuyor.")
                self.statusBar().showMessage("Afis kontrolu: eksik kayit yok")
                return

            dialog = QDialog(self)
            dialog.setWindowTitle("Eksik Afiş Raporu")
            dialog.setMinimumWidth(760)
            dialog.setMinimumHeight(520)
            dialog.setStyleSheet("QDialog { background-color: #0f1419; }")

            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(18, 16, 18, 16)
            layout.setSpacing(10)

            title_label = QLabel("🖼 Eksik / Gecersiz Afiş Bulundu")
            title_label.setStyleSheet("color: #60a5fa; font-size: 19px; font-weight: 700;")
            layout.addWidget(title_label)

            summary_label = QLabel(
                f"Toplam film: {len(rows)} | Eksik afis: {len(missing_entries)} | Gecersiz URL: {len(invalid_entries)}"
            )
            summary_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
            layout.addWidget(summary_label)

            report_box = QTextEdit()
            report_box.setReadOnly(True)
            report_box.setStyleSheet("""
                QTextEdit {
                    background-color: #111827;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    color: #e2e8f0;
                    padding: 10px;
                    font-size: 12px;
                }
            """)

            report_lines = []
            if missing_entries:
                report_lines.append("Eksik afis baglantisi olan filmler:")
                report_lines.extend([f"- ({movie_id}) {title}" for movie_id, title in missing_entries[:200]])
                if len(missing_entries) > 200:
                    report_lines.append(f"... ve {len(missing_entries) - 200} film daha")
                report_lines.append("")

            if invalid_entries:
                report_lines.append("Gecersiz afis URL'si olan filmler:")
                report_lines.extend([f"- ({movie_id}) {title} -> {url}" for movie_id, title, url in invalid_entries[:200]])
                if len(invalid_entries) > 200:
                    report_lines.append(f"... ve {len(invalid_entries) - 200} film daha")

            report_box.setPlainText("\n".join(report_lines))
            layout.addWidget(report_box, 1)

            close_button = QPushButton("Kapat")
            close_button.setCursor(Qt.CursorShape.PointingHandCursor)
            close_button.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6);
                    color: #ffffff;
                    padding: 8px 18px;
                    border-radius: 8px;
                    font-size: 13px;
                    font-weight: 600;
                    border: none;
                    min-width: 100px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #2563eb);
                }
            """)
            close_button.clicked.connect(dialog.accept)
            layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)

            self.statusBar().showMessage(f"Afis kontrolu tamamlandi: {total_missing} sorunlu kayit")
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Afis kontrolu sirasinda hata olustu:\n{str(e)}")
        finally:
            self.return_connection(conn)

    def update_movie_summaries_from_omdb(self):
        """Veritabanindaki filmlerin ozetlerini OMDb ile dogrular ve gunceller."""
        if not self.ensure_omdb_api_key():
            return

        conn = self.get_connection()
        if not conn:
            QMessageBox.critical(self, "Hata", "Veritabani baglantisi kurulamadigi icin ozetler guncellenemedi.")
            return

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, year FROM movies ORDER BY id")
            movies = cursor.fetchall()
            if not movies:
                QMessageBox.information(self, "Bilgi", "Ozet guncellenecek film bulunamadi.")
                return

            updated_count = 0
            for movie_id, title, year in movies:
                params = {
                    "apikey": self.omdb_api_key,
                    "t": title,
                    "type": "movie",
                    "plot": "full"
                }
                if year:
                    params["y"] = year

                try:
                    response = requests.get(self.omdb_base_url, params=params, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                except Exception:
                    continue

                if data.get("Response") != "True":
                    continue

                plot = (data.get("Plot") or "").strip()
                if not plot or plot == "N/A":
                    continue

                cursor.execute(
                    "UPDATE movies SET description = %s WHERE id = %s",
                    (plot, movie_id)
                )
                updated_count += 1
                self.statusBar().showMessage(f"Ozet guncelleniyor: {updated_count}/{len(movies)}")

            conn.commit()
            QMessageBox.information(
                self,
                "Basarili",
                f"Ozet guncelleme tamamlandi.\nGuncellenen film sayisi: {updated_count}"
            )
            self.statusBar().showMessage(f"Ozet guncelleme bitti: {updated_count} film")
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "Hata", f"Ozetler guncellenirken hata olustu:\n{str(e)}")
        finally:
            self.return_connection(conn)

    def prepare_database_for_ml(self):
        """Veritabanini model egitimi icin ozellik ve etkileşim verisiyle hazirla."""
        conn = self.get_connection()
        if not conn:
            QMessageBox.critical(self, "Hata", "Veritabani baglantisi kurulamadigi icin ML hazirlik yapilamadi.")
            return

        try:
            cursor = conn.cursor()
            self.refresh_recommendation_features(cursor=cursor, rebuild_movie_categories=True)
            self.refresh_ml_training_assets(cursor=cursor)

            cursor.execute("SELECT COUNT(*) FROM movies")
            movie_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM profiles")
            profile_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM interaction_events")
            interaction_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM movie_categories")
            category_mapping_count = cursor.fetchone()[0]

            conn.commit()
            QMessageBox.information(
                self,
                "ML Hazirlik Tamamlandi",
                "Veritabani makine egitimi icin hazirlandi.\n\n"
                f"Film: {movie_count}\n"
                f"Profil: {profile_count}\n"
                f"Etkilesim: {interaction_count}\n"
                f"Film-Kategori eslesmesi: {category_mapping_count}\n\n"
                "Kullanilabilir view'lar:\n"
                "- recommendation_training_data\n"
                "- ml_training_interactions\n"
                "- ml_profile_feature_vectors"
            )
            self.statusBar().showMessage("ML veri hazirligi tamamlandi")
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "Hata", f"ML hazirlik sirasinda hata olustu:\n{str(e)}")
        finally:
            self.return_connection(conn)
    
    def show_omdb_search_dialog(self):
        """OMDb film arama dialogunu göster"""
        if not self.ensure_omdb_api_key():
            return
        
        # Film arama dialogu
        search_dialog = QDialog(self)
        search_dialog.setWindowTitle("OMDb'den Film Ara")
        search_dialog.setStyleSheet("QDialog { background-color: #1a1f2e; }")
        search_dialog.setMinimumWidth(400)
        layout = QVBoxLayout()
        
        search_input = QLineEdit()
        search_input.setPlaceholderText("Film adı girin (örn: Inception, The Matrix...)")
        search_input.setStyleSheet("""
            QLineEdit {
                background-color: #0f1419;
                color: #e2e8f0;
                border: 2px solid #2d3748;
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #3b82f6;
            }
        """)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(search_dialog.accept)
        buttons.rejected.connect(search_dialog.reject)
        buttons.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6);
                color: #ffffff;
                padding: 8px 20px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                border: none;
                min-width: 80px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #2563eb);
            }
        """)
        
        layout.addWidget(QLabel("Film Adı:"))
        layout.addWidget(search_input)
        layout.addWidget(buttons)
        search_dialog.setLayout(layout)
        
        if search_dialog.exec() == QDialog.DialogCode.Accepted:
            movie_title = search_input.text().strip()
            if movie_title:
                self.search_and_add_movie_from_omdb(movie_title)
    
    def search_and_add_movie_from_omdb(self, movie_title):
        """OMDb API'den film ara ve veritabanına ekle"""
        if not self.omdb_api_key:
            QMessageBox.warning(self, "Hata", "OMDb API Key tanımlı değil!")
            return
        
        try:
            self.statusBar().showMessage(f"'{movie_title}' aranıyor...")
            
            # OMDb API'den film ara
            params = {
                'apikey': self.omdb_api_key,
                't': movie_title,
                'type': 'movie',
                'plot': 'full'
            }
            
            response = requests.get(self.omdb_base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('Response') == 'False':
                error_msg = data.get('Error', 'Film bulunamadı')
                QMessageBox.warning(self, "Film Bulunamadı", f"{error_msg}\n\nLütfen film adını kontrol edin.")
                self.statusBar().showMessage("Film bulunamadı")
                return
            
            # Film bilgilerini al
            title = data.get('Title', '')
            year = data.get('Year', '')
            genre = data.get('Genre', '').strip() if data.get('Genre') else None
            rating_str = data.get('imdbRating', 'N/A')
            description = data.get('Plot', '')
            poster_url = data.get('Poster', '')
            actors = self._normalize_actor_list(data.get('Actors', ''))
            country = self._normalize_country_value(data.get('Country', ''))
            
            # Rating'i sayıya çevir
            try:
                rating = float(rating_str) if rating_str != 'N/A' else None
            except:
                rating = None
            
            # Yılı sayıya çevir
            try:
                year_int = int(year.split('–')[0]) if year else None
            except:
                year_int = None
            
            if not title:
                QMessageBox.warning(self, "Hata", "Film bilgileri alınamadı!")
                return
            
            # Veritabanına kaydet
            conn = self.get_connection()
            if not conn:
                QMessageBox.critical(self, "Hata", "Veritabanı bağlantısı kurulamadı!")
                return
            
            try:
                cursor = conn.cursor()
                
                # Film zaten var mı kontrol et
                cursor.execute("SELECT id FROM movies WHERE LOWER(title) = LOWER(%s)", (title,))
                existing = cursor.fetchone()
                
                if existing:
                    QMessageBox.information(self, "Bilgi", f"'{title}' zaten veritabanında mevcut!")
                    self.statusBar().showMessage("Film zaten mevcut")
                else:
                    # Yeni film ekle
                    cursor.execute("""
                        INSERT INTO movies (title, genre, year, rating, description, poster_url, actors, country)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (title, genre, year_int, rating, description, poster_url, actors, country))
                    self.refresh_recommendation_features(cursor=cursor, rebuild_movie_categories=True)
                    self.refresh_ml_training_assets(cursor=cursor)
                    conn.commit()
                    self.mark_content_recommender_dirty()
                    QMessageBox.information(self, "Başarılı", 
                                          f"'{title}' başarıyla veritabanına eklendi!\n\n"
                                          f"Yıl: {year}\n"
                                          f"Tür: {genre or 'Belirtilmemiş'}\n"
                                          f"IMDb Puanı: {rating_str}")
                    self.statusBar().showMessage(f"'{title}' eklendi")
                    
                    # Filmleri yenile
                    self.load_random_movies()
                    self.update_popular_movies(self.category_combo.currentText())
            
            except Exception as e:
                conn.rollback()
                QMessageBox.critical(self, "Veritabanı Hatası", 
                                    f"Film kaydedilirken hata oluştu:\n{str(e)}")
                self.statusBar().showMessage("Hata oluştu")
            finally:
                self.return_connection(conn)
        
        except requests.exceptions.RequestException as e:
            QMessageBox.critical(self, "API Hatası", 
                               f"OMDb API'ye bağlanılamadı:\n{str(e)}\n\n"
                               f"İnternet bağlantınızı kontrol edin.")
            self.statusBar().showMessage("API hatası")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Beklenmeyen bir hata oluştu:\n{str(e)}")
            self.statusBar().showMessage("Hata oluştu")


def main():
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("MOVIERSE")
        window = MovieRecommendationApp()
        window.raise_()  # Pencereyi öne getir
        window.activateWindow()  # Pencereyi aktif et
        window.show()  # Pencereyi göster
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("\nUygulama kullanıcı tarafından kapatıldı.")
        sys.exit(0)
    except Exception as e:
        error_msg = f"Uygulama başlatma hatası: {str(e)}"
        print(error_msg)
        print("=" * 60)
        import traceback
        traceback.print_exc()
        print("=" * 60)
        try:
            QMessageBox.critical(None, "Kritik Hata", 
                               f"Uygulama başlatılamadı:\n\n{str(e)}\n\n"
                               f"Detaylar için konsol çıktısına bakın.")
        except:
            # QMessageBox gösterilemezse sadece print
            print("\nHATA: Uygulama başlatılamadı!")
            print("Lütfen yukarıdaki hata mesajlarını kontrol edin.")
        input("\nDevam etmek için Enter'a basın...")
        sys.exit(1)


if __name__ == "__main__":
    main()
