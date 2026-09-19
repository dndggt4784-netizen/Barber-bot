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
            status TEXT NOT NULL DEFAULT 'active'
        )
        """
    )
    conn.commit()
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
