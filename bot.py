import yaml, time, os
from db import Database, Session, Order
from telegram.ext import Updater, CommandHandler
from telegram import ParseMode
from jinja2 import Environment, FileSystemLoader


def __get_order_details(order_string):
        order = ''
        quantity = 1 
        price = None
        for word in order_string.split(' '):
            # check quantity
            if word.endswith('x') and word[:word.find('x')].isdigit():
                quantity = int(word[:word.find('x')])
            # check price
            elif word.startswith('$') and word[1:].isdigit():
                price = float(word[1:])
            # check order
            else:
                order = word

        return quantity, order, price

# def __user_orders_msg(session, username):
#     orders = Order.objects.filter(session=session, username=username)
#     order_msg = 'Your orders:\n============\n'
#     for order in orders:
#         order_msg += '> {}x {} ${}\n'.format(
#             order.quantity, order.order, order.price
#         ) 
#     return order_msg

def __all_orders_msg(session):
    orders = Order.objects.filter(session=session)
    order_msg = 'All Orders:\n============\n'
    for order in orders:
        order_msg += '> @{} {}x {} ${}\n'.format(
            order.username, order.quantity, order.order, (order.price or '?')
        ) 
    return order_msg
    
def startSession(bot, update):
    chat_id = str(update.message.chat.id)
    username = update.message.from_user.username

    if Session.get(chat_id=chat_id):
        text = 'Can\'t start new session, please end the current session'
        bot.send_message(chat_id=chat_id, text=text)
        return 
    
    session = Session(chat_id=chat_id, created_by=username)
    session.save()

    text = 'New session is started'
    bot.send_message(chat_id=chat_id, text=text)

def endSession(bot, update):
    chat_id = str(update.message.chat.id)
    if Session.get(chat_id=chat_id):
        Session.get(chat_id=chat_id).delete()

    text = 'Session is ended'
    bot.send_message(chat_id=chat_id, text=text)


def setPrice(bot, update):
    chat_id = str(update.message.chat.id)
    session = Session.get(chat_id=chat_id)
    if not session:
        text = 'No actice session, please start a new one'
        bot.send_message(chat_id=chat_id, text=text)
        return

    order, price = update.message.text.replace('/set ', '').split('=')
    Order.objects(session=session, order=order).update(price=price)


def myOrders(bot, update):
    chat_id = str(update.message.chat.id)
    username = update.message.from_user.username    
    session = Session.get(chat_id=chat_id)

    if not session:
        text = 'No actice session, please start a new one'
        bot.send_message(chat_id=chat_id, text=text)
        return

    orders = Order.objects.filter(session=session, username=username)
    text = j2_env.get_template('user_orders.html').render(orders=orders, username=username)
    bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)


def allOrders(bot, update):
    chat_id = str(update.message.chat.id)
    session = Session.get(chat_id=chat_id)

    if not session:
        text = 'No actice session, please start a new one'
        bot.send_message(chat_id=chat_id, text=text)
        return

    orders = Order.objects.filter(session=session)
    text = j2_env.get_template('all_orders.html').render(orders=orders)
    bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)



def addOrder(bot, update):
    # import ipdb ; ipdb.set_trace()
    chat_id = str(update.message.chat.id)
    session = Session.get(chat_id=chat_id)

    if not session:
        update.message.reply_text('Please start a new session first')
        return

    username = update.message.from_user.username
    timestamp = time.time()
    payload = update.message.text.replace('/add ', '')
    orders = payload.split('+')

    for order_string in orders:
        quantity, order, price = __get_order_details(order_string.strip())

        if not price:
            exists_order_with_price = Order.get(session=session, order=order, price__ne=None)
            if exists_order_with_price:
                price = exists_order_with_price.price
        
        exists_order = Order.get(
            session=session, 
            username=username, 
            order=order
        )
        
        if exists_order:
            price = price or exists_order.price
            exists_order.update(inc__quantity=quantity, price=price)
        else: 
            order_object = Order(
                session=session,
                username=username,
                quantity=quantity,
                price=price,
                order=order
            )
            order_object.save()

    
            

        

        

def main():
    updater = Updater(config['telegram']['token'])
    
    updater.dispatcher.add_handler(CommandHandler('start', startSession))
    updater.dispatcher.add_handler(CommandHandler('end', endSession))
    updater.dispatcher.add_handler(CommandHandler('add', addOrder))
    updater.dispatcher.add_handler(CommandHandler('set', setPrice))
    updater.dispatcher.add_handler(CommandHandler('me', myOrders))
    updater.dispatcher.add_handler(CommandHandler('all', allOrders))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':

    with open('config.yaml', 'r') as config_file:
        config = yaml.load(config_file)

    db = Database()
    db.connect(** config['database'])

    # templates_dir = os.path.dirname(os.path.abspath(__file__) + '/templates')
    j2_env = Environment(loader=FileSystemLoader(searchpath='./templates'), trim_blocks=True)

    main()

    