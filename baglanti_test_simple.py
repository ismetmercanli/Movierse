"""
Basit PostgreSQL baglanti testi.
Bu script baglanti bilgilerini test eder.
"""

import sys
import traceback

try:
    import psycopg2
except ImportError:
    print("HATA: psycopg2-binary yuklu degil!")
    print("Yuklemek icin: pip install psycopg2-binary")
    input("\nDevam etmek icin Enter'a basin...")
    sys.exit(1)

from core_services import DBConfig, configure_windows_console


class DatabaseConnectionTester:
    def __init__(self) -> None:
        self.config = DBConfig.from_env()

    def _print_config(self) -> None:
        print("Baglanti Bilgileri:")
        print(f"  Host: {self.config['host']}")
        print(f"  Port: {self.config['port']}")
        print(f"  Database: {self.config['database']}")
        print(f"  User: {self.config['user']}")
        print(f"  Password: {'*' * len(self.config['password'])}")
        print()
        print("-" * 60)
        print()

    def run(self) -> bool:
        print("=" * 60)
        print("PostgreSQL Baglanti Testi")
        print("=" * 60)
        print()
        self._print_config()

        try:
            print("Baglanti deneniyor...")
            conn = psycopg2.connect(**self.config)
            print("SUCCESS! Baglanti basarili!\n")

            cursor = conn.cursor()
            cursor.execute("SELECT current_database(), version();")
            db_info = cursor.fetchone()
            print(f"Baglanilan veritabani: {db_info[0]}")
            print(f"PostgreSQL versiyonu: {db_info[1].split(',')[0]}\n")

            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'movies'
                """
            )
            table_exists = cursor.fetchone()

            if table_exists:
                print("SUCCESS! 'movies' tablosu mevcut.")
                cursor.execute("SELECT COUNT(*) FROM movies")
                count = cursor.fetchone()[0]
                print(f"Tabloda {count} kayit var.")
            else:
                print("UYARI: 'movies' tablosu bulunamadi.")
                print("Tabloyu olusturmak icin main.py'yi calistirin.")

            conn.close()
            print()
            print("=" * 60)
            print("TEST BASARILI!")
            print("=" * 60)
            return True

        except psycopg2.OperationalError as exc:
            error_msg = str(exc)
            print("\n" + "=" * 60)
            print("BAGLANTI HATASI!")
            print("=" * 60)
            print()
            print(f"Hata: {error_msg}\n")

            if "could not connect" in error_msg.lower() or "connection refused" in error_msg.lower():
                print("COZUM:")
                print("1. PostgreSQL servisinin calistigindan emin olun")
                print("2. Host ve Port bilgilerini kontrol edin")
                print("3. Firewall ayarlarini kontrol edin")
            elif "authentication failed" in error_msg.lower() or "password" in error_msg.lower():
                print("COZUM:")
                print("1. Sifrenin dogru oldugundan emin olun")
                print("2. pgAdmin 4'te kullandiginiz sifreyi kullanin")
                print("3. Sifreyi ayarlamak icin: set DB_PASSWORD=sizin_sifreniz")
            elif "database" in error_msg.lower() and "does not exist" in error_msg.lower():
                print("COZUM:")
                print(f"1. '{self.config['database']}' veritabanini olusturun")
                print("2. pgAdmin 4 > Databases > Create > Database")
            else:
                print("COZUM:")
                print("1. Hata mesajini detayli kontrol edin")
                print("2. pgAdmin 4'te baglantiyi test edin")
                print("3. PostgreSQL log dosyalarini inceleyin")

            print()
            return False
        except Exception as exc:
            print("\n" + "=" * 60)
            print("BEKLENMEYEN HATA!")
            print("=" * 60)
            print()
            print(f"Hata: {exc}\n")
            traceback.print_exc()
            print()
            return False


if __name__ == "__main__":
    configure_windows_console()
    success = DatabaseConnectionTester().run()
    print()
    if not success:
        print("Baglanti testi basarisiz!")
        print("Lutfen yukaridaki cozum onerilerini deneyin.")
    print()
    input("Devam etmek icin Enter'a basin...")
