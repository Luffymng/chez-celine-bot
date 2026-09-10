from aiogram.fsm.state import State, StatesGroup


class BookingState(StatesGroup):
    choosing_date = State()
    choosing_guests = State()
    choosing_duration = State()
    choosing_service = State()
    choosing_master = State()
    choosing_time = State()
    entering_name = State()
    entering_phone = State()
    entering_comment = State()
    confirming = State()
