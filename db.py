import sqlite3
from datetime import datetime, timedelta

DB_PATH = "bookings.db"


def init_db():
    """Создаёт таблицу записей, если её ещё нет. Вызывается один раз при старте."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            client_name TEXT NOT NULL,
            client_phone TEXT NOT NULL,
            service_name TEXT NOT NULL,
            service_price INTEGER NOT NULL,
            booking_date TEXT NOT NULL,
            booking_time TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            client_reminded INTEGER NOT NULL DEFAULT 0,
            admin_reminded INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    # На случай обновления уже существующей базы без этих колонок
    for column in ("client_reminded", "admin_reminded"):
        try:
            conn.execute(f"ALTER TABLE bookings ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # колонка уже есть
    conn.close()


def get_booked_times(booking_date: str) -> set[str]:
    """Возвращает уже занятые слоты времени на указанную дату (формат YYYY-MM-DD)."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT booking_time FROM bookings WHERE booking_date = ? AND status = 'active'",
        (booking_date,),
    ).fetchall()
    conn.close()
    return {row[0] for row in rows}


def create_booking(
    user_id: int,
    client_name: str,
    client_phone: str,
    service_name: str,
    service_price: int,
    booking_date: str,
    booking_time: str,
) -> int:
    """Сохраняет новую запись в базу и возвращает её ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        """
        INSERT INTO bookings
            (user_id, client_name, client_phone, service_name, service_price,
             booking_date, booking_time, created_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """,
        (
            user_id,
            client_name,
            client_phone,
            service_name,
            service_price,
            booking_date,
            booking_time,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    booking_id = cursor.lastrowid
    conn.close()
    return booking_id


def cancel_booking(booking_id: int, user_id: int) -> bool:
    """Отменяет запись. Возвращает True, если запись найдена и принадлежит этому пользователю."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        "UPDATE bookings SET status = 'cancelled' WHERE id = ? AND user_id = ? AND status = 'active'",
        (booking_id, user_id),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def get_bookings_needing_client_reminder(target_date: str):
    """Активные записи на target_date (YYYY-MM-DD), которым ещё не отправлено напоминание клиенту."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT id, user_id, client_name, service_name, booking_date, booking_time
        FROM bookings
        WHERE status = 'active' AND booking_date = ? AND client_reminded = 0
        """,
        (target_date,),
    ).fetchall()
    conn.close()
    return rows


def get_active_bookings_for_date_needing_admin_reminder(target_date: str):
    """Все активные записи на target_date, которым ещё не отправлено напоминание админу.
    Фильтрацию по времени ('через час') делает вызывающий код, чтобы поддерживать любые слоты (00/30 мин)."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT id, user_id, client_name, client_phone, service_name, booking_date, booking_time
        FROM bookings
        WHERE status = 'active' AND booking_date = ? AND admin_reminded = 0
        """,
        (target_date,),
    ).fetchall()
    conn.close()
    return rows


def mark_client_reminded(booking_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE bookings SET client_reminded = 1 WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()


def mark_admin_reminded(booking_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE bookings SET admin_reminded = 1 WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()


def get_active_booking_for_user(user_id: int):
    """Возвращает последнюю активную запись пользователя (для кнопки 'Отменить запись')."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        """
        SELECT id, service_name, booking_date, booking_time
        FROM bookings
        WHERE user_id = ? AND status = 'active'
        ORDER BY id DESC LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    conn.close()
    return row
