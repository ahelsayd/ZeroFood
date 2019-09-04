import yaml, os, mongoengine, re
from db import Session, Order, UserSession
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters,
)
from telegram import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from jinja2 import Environment, FileSystemLoader
from functools import wraps
from difflib import get_close_matches


ORDER_URL = "https://telegram.me/otlobbot?start={chat_id}"


def private(func):
    @wraps(func)
    def decorator(*args, **kwargs):
        bot, update = args
        username = update.effective_user.username
        chat_id = update.effective_message.chat.id
        user_session = UserSession.get(username=username)
        if not user_session:
            update.message.reply_text("No active session")
            return

        session = user_session.session
        kwargs.update(session=session, username=username, chat_id=chat_id)
        return func(*args, **kwargs)

    return decorator


def group(func):
    @wraps(func)
    def decorator(*args, **kwargs):
        bot, update = args
        username = update.effective_user.username
        chat_id = str(update.effective_message.chat.id)
        session = Session.get(chat_id=chat_id)
        if not session:
            update.message.reply_text("No active session")
            return

        kwargs.update(session=session, username=username, chat_id=chat_id)
        return func(*args, **kwargs)

    return decorator


def is_digit(string):
    try:
        float(string)
        return True
    except ValueError:
        return False


def add_order_handler(message, username, session):
    orders = message.text.strip().split("+")
    for order_string in orders:
        quantity, order = extract_order_details(order_string.strip(), session)
        if not order:
            return False

        price = None
        ex_order = Order.objects(
            session=session, username=username, order=order
        ).first()
        if ex_order:
            price = ex_order.price

        Order(
            session=session,
            username=username,
            quantity=quantity,
            order=order,
            message_id=message.message_id,
            price=price,
        ).save()

    return True


def extract_order_details(order_string, session):
    order = ""
    quantity = None
    orders_db = []

    all_orders = Order.objects(session=session)
    for item in all_orders:
        orders_db.extend(item.order.split())

    for word in order_string.split():
        if word.isdigit() and not quantity:
            quantity = int(word)
        else:
            if order:
                order += " "

            closest_matches = get_close_matches(word, set(list(orders_db)))
            if closest_matches:
                order += closest_matches[0]
            else:
                order += word

    quantity = quantity or 1
    return quantity, order


def render_template(template, **kwargs):
    return j2_env.get_template(template).render(**kwargs)


def round_to_payable_unit(value):
    resolution = 0.25
    return round(float(value) / resolution) * resolution


def all_orders(update, session, **kwargs):
    """
    List all orders when command /all is issued
    """
    pipeline = [
        {"$match": {"session": session.id}},
        {
            "$group": {
                "_id": {"order": "$order", "username": "$username"},
                "quantity": {"$sum": "$quantity"},
                "price": {"$first": "$price"},
            }
        },
        {
            "$group": {
                "_id": "$_id.order",
                "users": {
                    "$push": {
                        "username": "$_id.username",
                        "quantity": {"$sum": "$quantity"},
                    }
                },
                "quantity": {"$sum": "$quantity"},
                "price": {"$first": "$price"},
            }
        },
    ]
    orders = Order.objects.aggregate(*pipeline)
    return orders


def update_orders_list(bot, update, session):
    orders = all_orders(update, session)
    text = render_template("all.html", orders=orders)
    bot.edit_message_text(
        chat_id=session.chat_id,
        message_id=session.orders_message_id,
        text=text,
        parse_mode=ParseMode.HTML,
    )


# handlers
def show_help(bot, update):
    """
    Show help message when command /help is issued
    """
    chat_id = str(update.effective_message.chat.id)
    text = render_template("help.html")
    bot.send_message(text=text, chat_id=chat_id, parse_mode=ParseMode.HTML)


def start(bot, update):
    chat = update.effective_chat
    username = update.effective_user.username
    message = update.effective_message.text
    reply_markup = None

    if chat.type == "private":
        payload = message.replace("/start", "").strip()
        if not payload:
            update.message.reply_text(
                "Invalid session, Please press on 'Add Order' button in the group message"
            )
            return

        chat_id = payload
        session = Session.get(chat_id=chat_id)
        if not session:
            update.message.reply_text("Session is not active")
            return

        user_session = UserSession.get(username=username)
        if not user_session:
            user_session = UserSession(session=session, username=username)
            user_session.save()

    else:
        chat_id = str(chat.id)
        session = Session.get(chat_id=chat_id)
        if session:
            update.message.reply_text("Session is already active")
            return

        session = Session(chat_id=chat_id, created_by=username)
        session.save()
        button_list = [
            InlineKeyboardButton("🍔 Add Order", url=ORDER_URL.format(chat_id=chat_id)),
            InlineKeyboardButton("💰 Bill", callback_data="bill"),
        ]

        reply_markup = InlineKeyboardMarkup([button_list])
        bot.send_message(
            text="New session is started, Click on Add order to place your orders",
            chat_id=chat_id,
            reply_markup=reply_markup,
        )

        orders = []
        text = render_template("all.html", orders=orders)
        orders_message = bot.send_message(
            text=text, chat_id=session.chat_id, parse_mode=ParseMode.HTML
        )
        session.update(orders_message_id=orders_message.message_id)


@group
def end(bot, update, session, **kwargs):
    """
    End active session when command /end is issued
    """
    session.delete()
    chat_id = kwargs.get("chat_id")
    bot.send_message(text="Session is ended", chat_id=chat_id)


@group
def set_items_values(bot, update, session, **kwargs):
    """
    Set items values (orders, tax and service)
    """
    message = update.message.reply_to_message
    if message.message_id == session.values_message_id:
        items = message.text.splitlines()[2:]
        orders = items[:-2]
        values = update.message.text.strip().split()

        if not all([is_digit(v) for v in values]):
            return update.message.reply_text(
                "Invalid input, all values must be numerical"
            )

        if len(values) != len(items):
            return update.message.reply_text(
                "Invalid input, expected %s values but got %s"
                % (len(items), len(values))
            )

        for i, order in enumerate(orders):
            price = float(values[i])
            Order.objects(session=session, order=order).update(price=price, multi=True)

        session.update(tax=values[-2], service=values[-1])
        update_orders_list(bot, update, session)
        bill(bot, update)


@group
def bill(bot, update, session, **kwargs):
    """
    Show bill when command /bill is issued
    """
    orders_with_no_price = Order.objects(session=session, price=None).order_by("id")
    if orders_with_no_price:
        text = render_template("prices.html", orders=orders_with_no_price)
        message = bot.send_message(
            text=text,
            chat_id=session.chat_id,
            parse_mode=ParseMode.HTML,
            reply_markup=ForceReply(),
        )
        session.update(values_message_id=message.message_id)
    else:
        normalized_service = 0
        normalized_tax = 0
        service = session.service
        tax = session.tax

        number_of_users = len(Order.objects.distinct("username"))
        if number_of_users:
            normalized_service = service / number_of_users
            normalized_tax = tax / number_of_users

        pipeline = [
            {"$match": {"session": session.id}},
            {
                "$group": {
                    "_id": {"username": "$username"},
                    "net": {"$sum": {"$multiply": ["$price", "$quantity"]}},
                }
            },
            {
                "$addFields": {
                    "total": {"$add": ["$net", normalized_service, normalized_tax]}
                }
            },
        ]
        bill = Order.objects.aggregate(*pipeline)
        text = render_template("bill.html", bill=bill, service=service, tax=tax)
        bot.send_message(text=text, chat_id=session.chat_id, parse_mode=ParseMode.HTML)


@private
def my_orders(bot, update, session, username, chat_id, **kwargs):
    """
    List user's orders when command /me is issued
    """
    pipeline = [
        {"$match": {"session": session.id, "username": username}},
        {
            "$group": {
                "_id": {"order": "$order"},
                "quantity": {"$sum": "$quantity"},
                "price": {"$first": "$price"},
            }
        },
    ]
    orders = Order.objects.aggregate(*pipeline)
    msg = render_template("me.html", orders=orders)
    update.message.reply_text(msg, parse_mode=ParseMode.HTML)


@private
def add_order(bot, update, session, username, **kwargs):
    """
    Add new order(s) when command /add is issued
    """
    message = update.effective_message
    if not add_order_handler(message, username, session):
        update.message.reply_text("Invalid order")

    update_orders_list(bot, update, session)


@private
def update_order(bot, update, session, username, **kwargs):
    message = update.effective_message
    Order.objects(message_id=message.message_id).delete()
    if not add_order_handler(message, username, session):
        update.message.reply_text("Invalid order")

    update_orders_list(bot, update, session)


def callback_query_handler(bot, update):
    data = update.callback_query.data
    if data == "bill":
        bill(bot, update)


def main():
    updater = Updater(config["telegram"]["token"], use_context=False)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("help", show_help))
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("end", end))
    dp.add_handler(MessageHandler(Filters.private & Filters.update.message, add_order))
    dp.add_handler(
        MessageHandler(Filters.private & Filters.update.edited_message, update_order)
    )
    dp.add_handler(MessageHandler(Filters.reply, set_items_values))
    dp.add_handler(CallbackQueryHandler(callback_query_handler))
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    with open("config.yaml", "r") as config_file:
        config = yaml.safe_load(config_file)

    mongoengine.connect(**config["database"])
    j2_env = Environment(
        loader=FileSystemLoader(searchpath="./templates"), trim_blocks=True
    )
    j2_env.globals.update(round_to_payable_unit=round_to_payable_unit)
    main()
