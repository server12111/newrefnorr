import database


class PromoError(Exception):
    pass


async def activate_promo(telegram_id: int, code: str) -> float:
    promo = await database.get_promo(code)
    if not promo:
        raise PromoError("Промокод не найден.")
    if not promo["is_active"]:
        raise PromoError("Промокод больше не активен.")
    if promo["activations"] >= promo["max_activations"]:
        raise PromoError("Лимит активаций промокода исчерпан.")
    if await database.has_activated_promo(promo["id"], telegram_id):
        raise PromoError("Вы уже активировали этот промокод.")

    required = promo["required_tasks"] or 0
    if required:
        user = await database.get_user(telegram_id)
        if not user or user["tasks_completed"] < required:
            raise PromoError(f"Чтобы использовать этот промокод, нужно выполнить {required} заданий.")

    result = await database.activate_promo(promo["id"], telegram_id)
    if result == "already":
        raise PromoError("Вы уже активировали этот промокод.")
    if result == "limit":
        raise PromoError("Лимит активаций промокода исчерпан.")
    await database.adjust_balance(telegram_id, promo["reward"])
    await database.add_log(
        "promo",
        "activated",
        {"code": promo["code"], "user_id": telegram_id, "reward": promo["reward"]},
    )
    return promo["reward"]
