import re
from app.database.connection import connection
from app.utils.errors import ServiceError


def safe_memory(text):
    return not re.search(r"password|api[_ -]?key|access[_ -]?token|credit.?card|cvv|address|phone|email|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b\d{7,19}\b",text,re.I)


class MemoryService:
    def __init__(self, settings, embeddings, vectors):
        self.settings,self.embeddings,self.vectors=settings,embeddings,vectors

    def enabled(self, person_id):
        with connection(self.settings.database_path) as conn:
            row=conn.execute("SELECT memory_enabled FROM customer_preferences WHERE person_id=?",(person_id,)).fetchone()
            return bool(row[0]) if row else True

    def set_enabled(self,person_id,enabled):
        with connection(self.settings.database_path,write=True) as conn:
            conn.execute("INSERT INTO customer_preferences VALUES(?,?) ON CONFLICT(person_id) DO UPDATE SET memory_enabled=excluded.memory_enabled",(person_id,int(enabled)))
        return {"memory_enabled":enabled}

    def list(self,person_id):
        with connection(self.settings.database_path) as conn:
            return [dict(r) for r in conn.execute("SELECT memory_id,memory_key,text,version,updated_at FROM customer_memories WHERE person_id=? AND active=1 ORDER BY updated_at DESC LIMIT ?",(person_id,self.settings.memory_max_records))]

    def propose(self,person_id,proposals,source_message_id):
        if not self.enabled(person_id): return []
        saved=[]
        with connection(self.settings.database_path,write=True) as conn:
            source=conn.execute("SELECT m.content FROM conversation_messages m JOIN conversations c USING(conversation_id) WHERE message_id=? AND c.person_id=? AND m.role='user'",(source_message_id,person_id)).fetchone()
            if not source: raise ServiceError(404,"Memory source message not found")
            for proposal in proposals[:self.settings.memory_proposals_per_turn]:
                if proposal.source_quote.casefold() not in source[0].casefold() or not safe_memory(proposal.text+' '+proposal.source_quote): continue
                count=conn.execute("SELECT COUNT(*) FROM customer_memories WHERE person_id=? AND active=1",(person_id,)).fetchone()[0]
                old=conn.execute("SELECT * FROM customer_memories WHERE person_id=? AND memory_key=?",(person_id,proposal.key)).fetchone()
                if count>=self.settings.memory_max_records and (not old or not old['active']): continue
                if old and old['text']==proposal.text and old['active']: continue
                conn.execute("""INSERT INTO customer_memories(person_id,memory_key,text,source_message_id) VALUES(?,?,?,?)
                    ON CONFLICT(person_id,memory_key) DO UPDATE SET text=excluded.text,source_message_id=excluded.source_message_id,
                    active=1,version=version+1,updated_at=datetime('now')""",(person_id,proposal.key,proposal.text,source_message_id))
                row=conn.execute("SELECT * FROM customer_memories WHERE person_id=? AND memory_key=?",(person_id,proposal.key)).fetchone()
                self._job(conn,row,"upsert")
                saved.append(row['memory_id'])
        return saved

    @staticmethod
    def _job(conn,row,operation):
        conn.execute("INSERT INTO customer_memory_jobs(memory_id,version,operation) VALUES(?,?,?) ON CONFLICT(memory_id) DO UPDATE SET version=excluded.version,operation=excluded.operation,status='pending',error=NULL",(row['memory_id'],row['version'],operation))

    def edit(self,person_id,memory_id,text):
        if not safe_memory(text): raise ServiceError(400,"Credentials/payment details cannot be saved as memory")
        with connection(self.settings.database_path,write=True) as conn:
            row=conn.execute("SELECT * FROM customer_memories WHERE memory_id=? AND person_id=? AND active=1",(memory_id,person_id)).fetchone()
            if not row: raise ServiceError(404,"Memory not found")
            conn.execute("UPDATE customer_memories SET text=?,version=version+1,updated_at=datetime('now') WHERE memory_id=?",(text,memory_id))
            updated=conn.execute("SELECT * FROM customer_memories WHERE memory_id=?",(memory_id,)).fetchone()
            self._job(conn,updated,"upsert")
        return {"updated":True}

    def delete(self,person_id,memory_id=None):
        with connection(self.settings.database_path,write=True) as conn:
            rows=conn.execute("SELECT * FROM customer_memories WHERE person_id=? AND active=1"+(" AND memory_id=?" if memory_id is not None else ""),(person_id,memory_id) if memory_id is not None else (person_id,)).fetchall()
            if memory_id is not None and not rows: raise ServiceError(404,"Memory not found")
            for row in rows:
                # Immediately erase SQL text and bump version; stale vectors cannot be recalled.
                conn.execute("UPDATE customer_memories SET text='',active=0,version=version+1,source_message_id=NULL WHERE memory_id=?",(row['memory_id'],))
                self._job(conn,conn.execute("SELECT * FROM customer_memories WHERE memory_id=?",(row['memory_id'],)).fetchone(),"delete")
        return {"deleted":len(rows)}

    def recall(self,person_id,query):
        if not self.enabled(person_id) or not self.list(person_id): return [],False
        try:
            hits=self.vectors.search(person_id,self.embeddings.encode_query(query),self.settings.memory_recall_top_k)
            with connection(self.settings.database_path) as conn:
                memories=[]
                for memory_id,version,score in hits:
                    if score<self.settings.memory_min_score: continue
                    row=conn.execute("SELECT memory_id,text,version FROM customer_memories WHERE memory_id=? AND person_id=? AND active=1 AND version=?",(memory_id,person_id,version)).fetchone()
                    if row: memories.append(dict(row))
                return memories,False
        except Exception:
            # Never replace unavailable vector recall with unfiltered cross-user context.
            return [],True

    def sync(self,person_id=None,limit=10):
        counts={"done":0,"failed":0}
        with connection(self.settings.database_path) as conn:
            rows=[dict(r) for r in conn.execute("""SELECT m.*,j.operation FROM customer_memory_jobs j JOIN customer_memories m USING(memory_id)
                WHERE j.status!='done'"""+(" AND m.person_id=?" if person_id is not None else "")+" LIMIT ?",(person_id,limit) if person_id is not None else (limit,))]
        for row in rows:
            try:
                vector=None if row['operation']=='delete' else self.embeddings.encode_documents([row['text']])[0]
                with connection(self.settings.database_path,write=True) as conn:
                    fresh=conn.execute("SELECT version,operation,status FROM customer_memory_jobs WHERE memory_id=?",(row['memory_id'],)).fetchone()
                    if not fresh or fresh['version']!=row['version'] or fresh['operation']!=row['operation'] or fresh['status']=='done': continue
                    if row['operation']=='delete': self.vectors.delete(row['person_id'],row['memory_id'])
                    else: self.vectors.upsert(row,vector)
                    conn.execute("UPDATE customer_memory_jobs SET status='done',error=NULL WHERE memory_id=?",(row['memory_id'],))
                counts['done']+=1
            except Exception as exc:
                with connection(self.settings.database_path,write=True) as conn:
                    conn.execute("UPDATE customer_memory_jobs SET status='failed',error=? WHERE memory_id=? AND version=?",(type(exc).__name__,row['memory_id'],row['version']))
                counts['failed']+=1
        return counts
