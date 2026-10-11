import time
import pytest
from pydantic import ValidationError
from qdrant_client import QdrantClient
from app.config import Settings
from app.database.connection import connection
from app.authentication.service import SessionService, digest
from app.conversations.service import ConversationService
from app.customer_memory.service import MemoryService
from app.customer_memory.vector_index import MemoryVectorIndex
from app.customer_memory.schemas import MemoryProposal
from app.application_guide.schemas import UIAction
from app.agents.cart.schemas import CartDecision
from app.cart.service import CartService
from app.utils.errors import ServiceError


class Embeddings:
    def encode_query(self, query): return [1.,0.]
    def encode_documents(self, texts): return [[1.,0.] for _ in texts]


@pytest.fixture
def services(products):
    database, _, products = products
    with connection(database, write=True) as conn:
        for name in ['One','Two']:
            conn.execute("INSERT INTO person(first_name,last_name,email) VALUES(?,'Test',?)",(name,name+'@example.test'))
    settings = Settings(_env_file=None,database_path=database,embedding_dim=2)
    vectors = MemoryVectorIndex(settings,QdrantClient(':memory:'))
    yield settings, ConversationService(settings), MemoryService(settings,Embeddings(),vectors), products
    vectors.close()


def save_preference(conversations,memory,owner,text='I prefer tea',key='drink'):
    cid, _, _, lease = conversations.begin(owner)
    mid = conversations.save_turn(owner,cid,text,'Okay','Preference discussion',lease=lease)
    conversations.release(owner,cid,lease)
    ids=memory.propose(owner,[MemoryProposal(key=key,text=text,source_quote=text)],mid)
    return cid,mid,ids


def test_sessions_hash_csrf_expiry_and_revocation(services):
    settings,_,_,_=services
    sessions=SessionService(settings); token,csrf=sessions.issue(1)
    assert sessions.authenticate(token,csrf,write=True)==1
    with connection(settings.database_path) as conn:
        row=conn.execute('SELECT * FROM customer_sessions').fetchone()
        assert row['token_hash']==digest(token) and row['csrf_hash']!=csrf
    with pytest.raises(ServiceError): sessions.authenticate(token,'bad',write=True)
    with pytest.raises(ServiceError): sessions.authenticate('1')
    sessions.revoke(token)
    with pytest.raises(ServiceError): sessions.authenticate(token)
    token,csrf=sessions.issue(1)
    with connection(settings.database_path,write=True) as conn: conn.execute('UPDATE customer_sessions SET expires_at=0')
    with pytest.raises(ServiceError): sessions.authenticate(token)


def test_conversation_ownership_busy_and_clear(services):
    _,conversations,memory,_=services
    cid,mid,ids=save_preference(conversations,memory,1)
    with pytest.raises(ServiceError): conversations.messages(2,cid)
    cid,history,summary,lease=conversations.begin(1,cid)
    assert history[0]['content']=='I prefer tea' and summary=='Preference discussion'
    with pytest.raises(ServiceError): conversations.begin(1)
    with pytest.raises(ServiceError): conversations.clear(1)
    conversations.release(1,cid,lease)
    conversations.clear(1)
    assert memory.list(1)[0]['memory_id']==ids[0]
    with connection(memory.settings.database_path) as conn:
        assert conn.execute('SELECT source_message_id FROM customer_memories').fetchone()[0] is None


def test_expired_conversation_lease_cannot_release_or_save_new_turn(services):
    settings,conversations,_,_=services
    cid,_,_,old=conversations.begin(1)
    with connection(settings.database_path,write=True) as conn: conn.execute('UPDATE conversations SET busy_at=0')
    _,_,_,new=conversations.begin(1,cid)
    conversations.release(1,cid,old)
    with pytest.raises(ServiceError): conversations.save_turn(1,cid,'old','old',lease=old)
    conversations.save_turn(1,cid,'new','new',lease=new)
    conversations.release(1,cid,new)


def test_vector_memory_isolation_version_and_deletion(services):
    _,conversations,memory,_=services
    _,_,one=save_preference(conversations,memory,1)
    _,_,two=save_preference(conversations,memory,2,'I prefer coffee')
    assert memory.sync(limit=10)=={'done':2,'failed':0}
    recalled,degraded=memory.recall(1,'drink')
    assert not degraded and [r['memory_id'] for r in recalled]==one
    assert [r['memory_id'] for r in memory.recall(2,'drink')[0]]==two
    with pytest.raises(ServiceError): memory.edit(2,one[0],'changed')
    with pytest.raises(ServiceError): memory.delete(2,one[0])
    memory.edit(1,one[0],'I prefer green tea')
    assert memory.recall(1,'drink')[0]==[] # old vector version rejected
    memory.sync(1)
    assert memory.recall(1,'drink')[0][0]['text']=='I prefer green tea'
    memory.delete(1,one[0])
    assert memory.recall(1,'drink')[0]==[] # immediately revoked, before vector sync
    memory.sync(1)
    assert memory.vectors.search(1,[1.,0.],5)==[]
    assert memory.recall(2,'drink')[0]


def test_memory_explicit_source_private_data_and_disabled(services):
    _,conversations,memory,_=services
    cid,mid,_=save_preference(conversations,memory,1)
    assert memory.propose(1,[MemoryProposal(key='invented',text='I like milk',source_quote='milk')],mid)==[]
    with pytest.raises(ServiceError): memory.propose(2,[],mid)
    assert save_preference(conversations,memory,1,'My password is secret','secret')[2]==[]
    assert save_preference(conversations,memory,1,'My email is me@example.test','email')[2]==[]
    memory.set_enabled(1,False)
    assert save_preference(conversations,memory,1,'I prefer bread','bread')[2]==[]
    assert memory.recall(1,'drink')==([],False)
    assert memory.list(1) # disabling preserves records until explicit deletion


def test_stale_cart_revision_rejected_without_mutation(services):
    settings,_,_,products=services
    carts=CartService(settings.database_path)
    carts.update(1,[{'product_id':products[0]['product_id'],'quantity':1}],expected_revision=0)
    with pytest.raises(ServiceError): carts.update(1,[{'product_id':products[0]['product_id'],'quantity':2}],expected_revision=0)
    assert carts.view(1)['items'][0]['quantity']==1


def test_null_unused_cart_items_and_ui_action_boundaries():
    assert CartDecision(action='order_status',order_id=1,items=None).items==[]
    with pytest.raises(ValidationError): CartDecision(action='update_cart',items=None)
    for action in [{'action':'navigate','page':'https://evil.test'}, {'action':'execute','query':'script'}, {'action':'open_product','product_id':-1}]:
        with pytest.raises(ValidationError): UIAction.model_validate(action)
    with pytest.raises(ValidationError): Settings(_env_file=None,memory_collection='market_products')


def test_equivalent_product_navigation_forms_normalize_safely():
    normalized=UIAction.model_validate({'action':'navigate','page':'product','product_id':4,'query':None})
    assert normalized.action=='open_product' and normalized.product_id==4 and normalized.page is None
    normalized=UIAction.model_validate({'action':'open_product','page':'product','product_id':4})
    assert normalized.action=='open_product' and normalized.page is None
    with pytest.raises(ValidationError): UIAction.model_validate({'action':'navigate','page':'https://evil.test','product_id':4})
    with pytest.raises(ValidationError): UIAction.model_validate({'action':'navigate','page':'orders','product_id':4})
