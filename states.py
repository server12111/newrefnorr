from aiogram.fsm.state import State, StatesGroup


class PromoStates(StatesGroup):
    waiting_code = State()


class WithdrawStates(StatesGroup):
    waiting_username = State()
    confirming = State()


class AdminUserStates(StatesGroup):
    waiting_search = State()
    waiting_credit_amount = State()
    waiting_debit_amount = State()


class AdminPromoStates(StatesGroup):
    waiting_code = State()
    waiting_reward = State()
    waiting_limit = State()
    waiting_required_tasks = State()


class AdminSponsorStates(StatesGroup):
    waiting_name = State()
    waiting_url = State()
    waiting_channel_id = State()
    waiting_reward = State()
    waiting_click_goal = State()


class AdminBlocklistStates(StatesGroup):
    waiting_entry = State()


class AdminSettingsStates(StatesGroup):
    waiting_value = State()


class AdminMediaStates(StatesGroup):
    waiting_value = State()
    waiting_photo = State()


class AdminBroadcastStates(StatesGroup):
    waiting_content = State()
    confirming = State()


class AdminGiftStates(StatesGroup):
    waiting_text = State()
    waiting_target = State()
    confirming = State()
