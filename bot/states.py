from aiogram.fsm.state import State, StatesGroup


class LeaveApplicationStates(StatesGroup):
    leave_type = State()
    start_date = State()
    end_date = State()
    day_portion = State()
    reason = State()
    photo = State()
    confirmation = State()


class RegistrationStates(StatesGroup):
    full_name = State()
    ic_number = State()
    confirmation = State()
