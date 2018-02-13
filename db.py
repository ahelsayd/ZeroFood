from mongoengine import fields, Document, DoesNotExist, connect

class Database:
    def __init__(self):
        pass

    def connect(self, db, host, port, username=None, password=None):
        connect(
            db=db,
            host=host,
            port=port,
            username=username,
            password=password
        )


default_meta = {'allow_inheritance': True, "db_alias": 'telegram-bot'}

class DBModel(Document):
    meta = {'allow_inheritance': True, 'abstract': True}

    @classmethod
    def get(cls, **kwargs):
        try:
            return cls.objects.get(**kwargs)
        except DoesNotExist:
            return None

class Session(DBModel):
    chat_id = fields.StringField(unique=True, required=True)
    created_by = fields.StringField(required=True)
    # db collection
    meta = {"collection":"sessions"}

class Order(DBModel):
    session = fields.ReferenceField(Session, required=True, reverse_delete_rule=2)
    username = fields.StringField(required=True)
    order = fields.StringField(required=True)
    quantity = fields.IntField(default=1)
    price = fields.FloatField(default=None)
    # db collection
    meta = {"collection":"orders"}
