import secrets
import time
from app.database.connection import connection
from app.utils.errors import ServiceError


class ConversationService:
    def __init__(self, settings): self.settings = settings

    def begin(self, person_id, conversation_id=None):
        with connection(self.settings.database_path, write=True) as conn:
            if not conversation_id:
                conversation_id = secrets.token_urlsafe(24)
                conn.execute("INSERT INTO conversations(conversation_id,person_id) VALUES(?,?)", (conversation_id, person_id))
            row = conn.execute("SELECT * FROM conversations WHERE conversation_id=? AND person_id=?", (conversation_id,person_id)).fetchone()
            if not row: raise ServiceError(404, "Conversation not found")
            # Serialize customer turns across conversations too, since they share one cart.
            busy = conn.execute("SELECT 1 FROM conversations WHERE person_id=? AND busy=1 AND busy_at>?", (person_id,int(time.time())-self.settings.chat_turn_lock_seconds)).fetchone()
            if busy: raise ServiceError(409, "An assistant request is already running; wait for it to finish")
            lease = secrets.token_urlsafe(24)
            conn.execute("UPDATE conversations SET busy=1,busy_at=?,lock_token=? WHERE conversation_id=?", (int(time.time()),lease,conversation_id))
            history = [dict(r) for r in conn.execute("SELECT role,content FROM conversation_messages WHERE conversation_id=? ORDER BY message_id DESC LIMIT ?", (conversation_id,self.settings.customer_history_messages))][::-1]
            return conversation_id, history, row["summary"], lease

    def save_turn(self, person_id, conversation_id, query, answer, summary="", lease=None):
        with connection(self.settings.database_path, write=True) as conn:
            if not conn.execute("SELECT 1 FROM conversations WHERE conversation_id=? AND person_id=? AND busy=1 AND lock_token=?", (conversation_id,person_id,lease)).fetchone():
                raise ServiceError(409, "Conversation is no longer active")
            message_id=conn.execute("INSERT INTO conversation_messages(conversation_id,role,content) VALUES(?,'user',?)", (conversation_id,query)).lastrowid
            conn.execute("INSERT INTO conversation_messages(conversation_id,role,content) VALUES(?,'assistant',?)", (conversation_id,answer))
            conn.execute("UPDATE conversations SET summary=? WHERE conversation_id=?", (summary[:self.settings.conversation_summary_chars],conversation_id))
            return message_id

    def release(self, person_id, conversation_id, lease):
        with connection(self.settings.database_path, write=True) as conn:
            conn.execute("UPDATE conversations SET busy=0,busy_at=NULL,lock_token=NULL WHERE conversation_id=? AND person_id=? AND lock_token=?", (conversation_id,person_id,lease))

    def messages(self, person_id, conversation_id):
        with connection(self.settings.database_path) as conn:
            if not conn.execute("SELECT 1 FROM conversations WHERE conversation_id=? AND person_id=?", (conversation_id,person_id)).fetchone():
                raise ServiceError(404, "Conversation not found")
            return [dict(r) for r in conn.execute("SELECT role,content FROM conversation_messages WHERE conversation_id=? ORDER BY message_id DESC LIMIT ?", (conversation_id,self.settings.customer_history_messages))][::-1]

    def clear(self, person_id):
        with connection(self.settings.database_path,write=True) as conn:
            if conn.execute("SELECT 1 FROM conversations WHERE person_id=? AND busy=1 AND busy_at>?", (person_id,int(time.time())-self.settings.chat_turn_lock_seconds)).fetchone():
                raise ServiceError(409, "Wait for the current assistant request to finish")
            conn.execute("DELETE FROM conversations WHERE person_id=?", (person_id,))
