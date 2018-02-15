import yaml, time, os
from db import Database, Session, Order
from telegram.ext import Updater, CommandHandler
from telegram import ParseMode
from jinja2 import Environment, FileSystemLoader

def __get_order_details(order_string):
        order = ''
        quantity = None
        for word in order_string.split(' '):
            #quantity
            if word.isdigit() and not quantity:
                quantity = int(word)
            # order
            else:
                if order:
                    order += ' '
                order += word

        quantity = quantity or 1

        return quantity, order

def showHelp(bot, update):
    chat_id = str(update.message.chat.id)
    text = j2_env.get_template('help.html').render()
    bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)

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
        return

    orders = update.message.text.replace('/set ', '').split(',')
    for order in orders:
        order, price = [x.strip() for x in order.split('=')]
        if price.isdigit():
            Order.objects(session=session, order=order).update(price=price)

def myOrders(bot, update):
    chat_id = str(update.message.chat.id)
    username = update.message.from_user.username    
    session = Session.get(chat_id=chat_id)

    if not session:
        return

    orders = Order.objects.filter(session=session, username=username)
    text = j2_env.get_template('me.html').render(orders=orders, username=username)
    update.message.reply_text(text=text, parse_mode=ParseMode.HTML)

def allOrders(bot, update):
    chat_id = str(update.message.chat.id)
    session = Session.get(chat_id=chat_id)

    if not session:
        return

    pipeline = [
        {'$match': {
            'session':session.id
            }
        },
        {
            '$group':{
                '_id':{'order':'$order'}, 
                'quantity':{'$sum': "$quantity"}, 
                'price':{'$first':'$price'}, 
                'users':{'$push':{'username':'$username', 'quantity':'$quantity'}}
            }
        }
    ]

    orders = Order.objects.aggregate(*pipeline)
    text = j2_env.get_template('all.html').render(orders=orders)
    bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)

def bill(bot, update):
    chat_id = str(update.message.chat.id)
    session = Session.get(chat_id=chat_id)

    if not session:
        return

    pipeline = [
        {
            '$match': {'session':session.id}
        },
        {
            '$group':{
                '_id':{'username':'$username'},
                'bill':{'$sum':{'$multiply':["$price", "$quantity"]}}
            }
        }
    ]

    unknown_orders = Order.objects(price=None)
    bill = Order.objects.aggregate(*pipeline)
    text = j2_env.get_template('bill.html').render(bill=bill, unknown_orders=unknown_orders)
    bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)

def addOrder(bot, update):
    chat_id = str(update.message.chat.id)
    session = Session.get(chat_id=chat_id)
    username = update.message.from_user.username

    if not session:
        return

    if update.message.reply_to_message:
        payload = update.message.reply_to_message.text.replace('/add', '')
    else:
        payload = update.message.text.replace('/add', '')

    orders = payload.split('+')

    for order_string in orders:
        quantity, order = __get_order_details(order_string.strip())
        
        exists_order = Order.get(
            session=session, 
            username=username, 
            order=order
        )
        
        if exists_order:
            exists_order.update(inc__quantity=quantity)
        else: 
            order_object = Order(
                session=session,
                username=username,
                quantity=quantity,
                order=order
            )
            order_object.save()

def deleteOrder(bot, update):
    chat_id = str(update.message.chat.id)
    session = Session.get(chat_id=chat_id)
    username = update.message.from_user.username

    if not session:
        return

    if update.message.reply_to_message:
        payload = update.message.reply_to_message.text.replace('/add', '')
    else:
        payload = update.message.text.replace('/delete', '')

    orders = payload.split('+')

    for order_string in orders:
        quantity, order = __get_order_details(order_string.strip())
        
        quantity = abs(int(quantity))

        order_obj = Order.get(session=session, username=username, order=order)
        if order_obj:
            if quantity >= order_obj.quantity:
                order_obj.delete()
            else:
                order_obj.update(inc__quantity= -quantity)


def main():
    updater = Updater(config['telegram']['token'])
    
    updater.dispatcher.add_handler(CommandHandler('start', startSession))
    updater.dispatcher.add_handler(CommandHandler('end', endSession))
    updater.dispatcher.add_handler(CommandHandler('add', addOrder))
    updater.dispatcher.add_handler(CommandHandler('delete', deleteOrder))
    updater.dispatcher.add_handler(CommandHandler('set', setPrice))
    updater.dispatcher.add_handler(CommandHandler('me', myOrders))
    updater.dispatcher.add_handler(CommandHandler('all', allOrders))
    updater.dispatcher.add_handler(CommandHandler('bill', bill))
    updater.dispatcher.add_handler(CommandHandler('help', showHelp))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':

    with open('config.yaml', 'r') as config_file:
        config = yaml.load(config_file)

    db = Database()
    db.connect(** config['database'])

    j2_env = Environment(loader=FileSystemLoader(searchpath='./templates'), trim_blocks=True)

    main()

    