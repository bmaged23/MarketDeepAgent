from app.agents.customer.agent import create_runner
from app.application_guide.schemas import UIAction
from app.application_guide.registry import application_help
from app.database.connection import connection
from app.utils.errors import ServiceError


class AssistantService:
    def __init__(self,settings,search,conversations,memory,runner_factory=None):
        self.settings,self.search,self.conversations,self.memory=settings,search,conversations,memory
        self.runner_factory=runner_factory or create_runner

    def context(self,person_id,page):
        data=page.model_dump()
        with connection(self.settings.database_path) as conn:
            for field,table in (("product_id","product"),("category_id","category")):
                if data[field] is not None and not conn.execute(f"SELECT 1 FROM {table} WHERE {field}=?",(data[field],)).fetchone():
                    data[field]=None
            from app.products.queries import get_product
            selected = get_product(conn, data['product_id']) if data['product_id'] else None
            actual={r[0] for r in conn.execute("SELECT product_id FROM product")}
            data['visible_product_ids']=[i for i in data['visible_product_ids'] if i in actual]
            data['referenced_product_ids']=[i for i in data['referenced_product_ids'] if i in actual]
            referenced = [get_product(conn, i) for i in dict.fromkeys(data['referenced_product_ids'])]
            visible = [get_product(conn, i) for i in dict.fromkeys(data['visible_product_ids'])] if data['page'] == 'shop' else []
            categories = [dict(row) for row in conn.execute("SELECT category_id,name FROM category ORDER BY category_id")]
            profile=dict(conn.execute("SELECT first_name,last_name,phone,address FROM person WHERE person_id=?",(person_id,)).fetchone())
        return {"categories":categories,"page_context":data,"selected_product":selected,"referenced_products":referenced,"visible_products":visible,"application_help":application_help(),"profile":profile,
                "settings":{"memory_enabled":self.memory.enabled(person_id)}}

    def chat(self,person_id,payload):
        conversation_id,history,summary,lease=self.conversations.begin(person_id,payload.conversation_id)
        try:
            recalled,degraded=self.memory.recall(person_id,payload.query)
            context=self.context(person_id,payload.page_context)
            context.update(memories=recalled,conversation_summary=summary)
            runner=self.runner_factory(self.settings,self.search,person_id)
            result=runner.run(payload.query,history=history,context=context)
            actions=[]
            approved_ids = {p['product_id'] for p in [*context['referenced_products'], *context['visible_products']]}
            if context['selected_product']: approved_ids.add(context['selected_product']['product_id'])
            for section in result.get('results', {}).get('retrieval', {}).get('sections', []):
                approved_ids.update(chunk['product']['product_id'] for chunk in section.get('chunks', []) if chunk.get('approval') == 1 and chunk.get('product'))
            # Cards can come from current context as well as a new retrieval. Hydrate
            # only verified IDs from SQL; model prose/guessed IDs are never card data.
            card_ids = list(result.pop('product_ids', []))
            for section in result.get('results', {}).get('retrieval', {}).get('sections', []):
                card_ids.extend(c['product']['product_id'] for c in section.get('chunks', []) if c.get('approval') == 1 and c.get('product'))
            with connection(self.settings.database_path) as conn:
                from app.products.catalog_query import project_product
                from app.products.queries import get_product
                result['products'] = [project_product(product) for product_id in dict.fromkeys(card_ids)
                    if type(product_id) is int and product_id in approved_ids
                    and (product := get_product(conn, product_id)) is not None]
                for action in result.get('actions',[]):
                    action = UIAction.model_validate(action).model_dump()
                    if action['action']=='open_product' and (action['product_id'] not in approved_ids or not conn.execute("SELECT 1 FROM product WHERE product_id=?",(action['product_id'],)).fetchone()): continue
                    if action.get('category_id') and not conn.execute("SELECT 1 FROM category WHERE category_id=?",(action['category_id'],)).fetchone(): continue
                    actions.append(action)
            message_id=self.conversations.save_turn(person_id,conversation_id,payload.query,result['answer'],result.get('conversation_summary') or summary,lease=lease)
            from app.customer_memory.schemas import MemoryProposal
            proposals=[MemoryProposal.model_validate(p) for p in result.get('memory_proposals',[])]
            saved=self.memory.propose(person_id,proposals,message_id)
            # Sync this customer's queued updates/deletes, including failed retries, with bounded work.
            synchronization=self.memory.sync(person_id,self.settings.memory_sync_batch_size)
            result.update(conversation_id=conversation_id,actions=actions,memory_status={"saved":len(saved),"recall_degraded":degraded,"sync":synchronization})
            result.pop('memory_proposals',None)
            result.pop('conversation_summary',None)
            return result
        finally:
            self.conversations.release(person_id,conversation_id,lease)
