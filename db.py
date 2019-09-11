from mongoengine import fields, Document, DoesNotExist


class DBModel(Document):
    meta = {"allow_inheritance": True, "abstract": True}

    @classmethod
    def get(cls, **kwargs):
        try:
            return cls.objects.get(**kwargs)
        except DoesNotExist:
            return None


class Session(DBModel):
    chat_id = fields.StringField(unique=True, required=True)
    created_by = fields.StringField(required=True)
    service = fields.FloatField(default=0)
    tax = fields.FloatField(default=0)
    orders_message_id = fields.IntField()
    values_message_id = fields.IntField()
    is_open = fields.BooleanField(default=True)
    meta = {"collection": "sessions"}


class UserSession(DBModel):
    username = fields.StringField(required=True, unique=True)
    session = fields.ReferenceField(Session, required=True, reverse_delete_rule=2)
    meta = {"collection": "user_session"}


class Order(DBModel):
    session = fields.ReferenceField(Session, required=True, reverse_delete_rule=2)
    username = fields.StringField(required=True)
    order = fields.StringField(required=True)
    quantity = fields.IntField(default=1)
    price = fields.FloatField(default=None)
    message_id = fields.IntField(required=True)
    meta = {"collection": "orders"}
