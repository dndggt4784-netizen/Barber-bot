import asyncio
import logging
from datetime import date, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

import config
import db

logging.basicConfig(level=logging.INFO)
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

WEEKDAYS_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


class Booking(StatesGroup):
    choosing_date = State()
    choosing_time = State()
    entering_name = State()
    entering_phone = State()


# ---------- Клавиатуры ----------

def services_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{name} — {price} ₴", callback_data=f"service:{i}")]
        for i, (name, price) in enumerate(config.SERVICES)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dates_keyboard() -> InlineKeyboardMarkup:
    rows, row = [], []
    today = date.today()
    for i in range(config.DAYS_AHEAD):
        d = today + timedelta(days=i)
        label = "Сегодня" if i == 0 else "Завтра" if i == 1 else f"{d.day} {MONTHS_RU[d.month - 1]}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"date:{d.isoformat()}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def times_keyboard(booking_date: str) -> InlineKeyboardMarkup:
    booked = db.get_booked_times(booking_date)
    free_slots = [t for t in config.TIME_SLOTS if t not in booked]
    rows, row = [], []
    for slot in free_slots:
        row.append(InlineKeyboardButton(text=slot, callback_data=f"time:{slot}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows), len(free_slots) > 0


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def format_date_human(iso_date: str) -> str:
    d = date.fromisoformat(iso_date)
    return f"{d.day} {MONTHS_RU[d.month - 1]}"


# ---------- Хендлеры ----------

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Привет! 👋 Я помогу записаться в {config.BUSINESS_NAME}.\n\n"
        f"Выберите услугу:",
        reply_markup=services_keyboard(),
    )


@dp.callback_query(F.data.startswith("service:"))
async def choose_service(callback: CallbackQuery, state: FSMContext):
    index = int(callback.data.split(":")[1])
    name, price = config.SERVICES[index]
    await state.update_data(service_name=name, service_price=price)
    await state.set_state(Booking.choosing_date)
    await callback.message.edit_text(
        f"Услуга: {name} — {price} ₴\n\nНа какой день записать?",
        reply_markup=dates_keyboard(),
    )
    await callback.answer()


@dp.callback_query(Booking.choosing_date, F.data.startswith("date:"))
async def choose_date(callback: CallbackQuery, state: FSMContext):
    booking_date = callback.data.split(":")[1]
    keyboard, has_slots = times_keyboard(booking_date)
    if not has_slots:
        await callback.answer("На эту дату свободных мест нет, выберите другой день", show_alert=True)
        return
    await state.update_data(booking_date=booking_date)
    await state.set_state(Booking.choosing_time)
    await callback.message.edit_text(
        f"Свободное время на {format_date_human(booking_date)}:",
        reply_markup=keyboard,
    )
    await callback.answer()


@dp.callback_query(Booking.choosing_time, F.data.startswith("time:"))
async def choose_time(callback: CallbackQuery, state: FSMContext):
    booking_time = callback.data.split(":", 1)[1]
    await state.update_data(booking_time=booking_time)
    await state.set_state(Booking.entering_name)
    await callback.message.edit_text("Как вас зовут?")
    await callback.answer()


@dp.message(Booking.entering_name)
async def enter_name(message: Message, state: FSMContext):
    await state.update_data(client_name=message.text.strip())
    await state.set_state(Booking.entering_phone)
    await message.answer(
        "Оставьте номер телефона для подтверждения записи:",
        reply_markup=phone_keyboard(),
    )


@dp.message(Booking.entering_phone, F.contact)
async def enter_phone_contact(message: Message, state: FSMContext):
    await finish_booking(message, state, message.contact.phone_number)


@dp.message(Booking.entering_phone, F.text)
async def enter_phone_text(message: Message, state: FSMContext):
    await finish_booking(message, state, message.text.strip())


async def finish_booking(message: Message, state: FSMContext, phone: str):
    data = await state.get_data()
    booking_date = data["booking_date"]
    booking_time = data["booking_time"]

    # Проверяем, что слот ещё не заняли, пока клиент вводил имя/телефон
    if booking_time in db.get_booked_times(booking_date):
        await message.answer(
            "Это время уже заняли. Пожалуйста, начните запись заново: /start",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()
        return

    booking_id = db.create_booking(
        user_id=message.from_user.id,
        client_name=data["client_name"],
        client_phone=phone,
        service_name=data["service_name"],
        service_price=data["service_price"],
        booking_date=booking_date,
        booking_time=booking_time,
    )

    human_date = format_date_human(booking_date)

    await message.answer(
        f"✅ Запись подтверждена!\n\n"
        f"{data['service_name']} — {data['service_price']} ₴\n"
        f"{human_date}, {booking_time}\n"
        f"{config.BUSINESS_NAME}, {config.BUSINESS_ADDRESS}\n\n"
        f"Напомним за день до визита.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.clear()

    if config.ADMIN_CHAT_ID:
        try:
            await bot.send_message(
                config.ADMIN_CHAT_ID,
                f"🆕 Новая запись #{booking_id}\n\n"
                f"Клиент: {data['client_name']}\n"
                f"Телефон: {phone}\n"
                f"Услуга: {data['service_name']} — {data['service_price']} ₴\n"
                f"Дата: {human_date}, {booking_time}",
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление админу: {e}")


@dp.message(F.text == "/cancel")
async def cmd_cancel(message: Message):
    booking = db.get_active_booking_for_user(message.from_user.id)
    if not booking:
        await message.answer("У вас нет активных записей.")
        return
    booking_id, service_name, booking_date, booking_time = booking
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Отменить запись", callback_data=f"cancel:{booking_id}")]]
    )
    await message.answer(
        f"Ваша запись: {service_name}, {format_date_human(booking_date)} в {booking_time}",
        reply_markup=keyboard,
    )


@dp.callback_query(F.data.startswith("cancel:"))
async def cancel_booking_handler(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])
    success = db.cancel_booking(booking_id, callback.from_user.id)
    if success:
        await callback.message.edit_text("Запись отменена. Будем рады видеть вас в другой раз! /start")
    else:
        await callback.answer("Не удалось отменить запись", show_alert=True)


async def main():
    db.init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
