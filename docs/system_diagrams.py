"""Source-backed, focused architecture views. No customer/runtime data is read."""
from html import escape
from pathlib import Path

COLORS = {'request': '#7dd3fc', 'response': '#c4b5fd', 'write': '#fbbf24', 'sync': '#5eead4'}

class Diagram:
    def __init__(self, title, subtitle, height=1000):
        self.height=height; self.nodes={}; self.layers=[]; self.cards=[]; self.paths=[]; self.labels=[]
        self.title=title; self.subtitle=subtitle

    def lane(self, x,y,w,h,title,subtitle):
        self.layers.append(f'<rect class="lane" x="{x}" y="{y}" width="{w}" height="{h}" rx="22"/><text class="lane-title" x="{x+24}" y="{y+31}">{escape(title)}</text><text class="muted" x="{x+24}" y="{y+53}">{escape(subtitle)}</text>')

    def node(self,key,x,y,w,title,lines,kind='SERVICE',color='request',detail=None):
        h=120; self.nodes[key]=(x,y,w,h); c=COLORS[color]
        detail=detail or ' '.join(lines)
        self.cards.append(f'<g class="node" tabindex="0" role="button" aria-label="{escape(title)}" data-detail="{escape(detail,quote=True)}"><title>{escape(detail)}</title><rect class="card" x="{x}" y="{y}" width="{w}" height="{h}" rx="15"/><rect x="{x+18}" y="{y+18}" width="3" height="15" rx="1" fill="{c}"/><text class="tag" x="{x+30}" y="{y+30}" fill="{c}">{escape(kind)}</text><text class="title" x="{x+18}" y="{y+58}">{escape(title)}</text>' + ''.join(f'<text class="body" x="{x+18}" y="{y+82+i*18}">{escape(line)}</text>' for i,line in enumerate(lines))+'</g>')

    def anchor(self,key,side,offset=0):
        x,y,w,h=self.nodes[key]
        return {'t':(x+w/2+offset,y),'b':(x+w/2+offset,y+h),'l':(x,y+h/2+offset),'r':(x+w,y+h/2+offset)}[side]

    def edge(self,a,b,label,side_a='b',side_b='t',kind='request',via=(),offset_a=0,offset_b=0,label_at=None):
        start=self.anchor(a,side_a,offset_a); end=self.anchor(b,side_b,offset_b)
        points=[start,*via,end]; d='M '+' L '.join(f'{x:g} {y:g}' for x,y in points); c=COLORS[kind]
        self.paths.append(f'<g class="connection {kind}"><title>{escape(label)}: {escape(a)} → {escape(b)}</title><path class="flow" d="{d}" stroke="{c}" marker-end="url(#{kind})"/><circle class="signal" r="3.5" fill="{c}"><animateMotion dur="3.5s" repeatCount="indefinite" path="{d}"/></circle></g>')
        if label_at:
            x,y=label_at; w=len(label)*7+18
            self.labels.append(f'<g><rect x="{x-w/2}" y="{y-13}" width="{w}" height="23" rx="7" fill="#0c1729"/><text class="edge-label" x="{x}" y="{y+3}" text-anchor="middle" fill="{c}">{escape(label)}</text></g>')

    def save(self,path):
        markers=''.join(f'<marker id="{key}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M 1 1 L 9 5 L 1 9" fill="none" stroke="{c}" stroke-width="2"/></marker>' for key,c in COLORS.items())
        header=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1400 {self.height}" role="img" aria-labelledby="heading desc"><title id="heading">{escape(self.title)}</title><desc id="desc">{escape(self.subtitle)}. Arrowheads show call, return and write directions. Motion is illustrative.</desc><defs>{markers}<linearGradient id="bg" x2="1" y2="1"><stop stop-color="#101e33"/><stop offset="1" stop-color="#060e1c"/></linearGradient></defs><style>
text{{font-family:system-ui,-apple-system,Arial,sans-serif}}.heading{{fill:#f0f6ff;font-size:30px;font-weight:700}}.muted{{fill:#94a9c4;font-size:13px}}.lane{{fill:#102039;fill-opacity:.55;stroke:#263d5b}}.lane-title{{fill:#d6e6fa;font-size:15px;font-weight:600;letter-spacing:1px}}.card{{fill:#14253d;stroke:#3a5575}}.title{{fill:#f0f6ff;font-size:19px;font-weight:650}}.body{{fill:#b4c6dd;font-size:13px}}.tag{{font-size:10px;font-weight:700;letter-spacing:1.6px}}.node:hover .card,.node:focus .card{{stroke:#e2e8f0;stroke-width:2}}.flow{{fill:none;stroke-width:2;stroke-linejoin:round}}.response .flow{{stroke-dasharray:6 5}}.sync .flow{{stroke-dasharray:3 5}}.edge-label{{font-size:12px}}@media(prefers-reduced-motion:reduce){{.signal{{display:none}}}}
</style><rect width="1400" height="{self.height}" fill="url(#bg)"/><text class="heading" x="40" y="48">{escape(self.title)}</text><text class="muted" x="40" y="76">{escape(self.subtitle)}</text>'''
        footer=f'<text class="muted" x="40" y="{self.height-24}">SOURCE-BACKED ARCHITECTURE  /  Motion illustrates direction; it is not runtime telemetry.</text>'
        Path(path).write_text(header+''.join(self.layers+self.paths+self.cards+self.labels)+footer+'</svg>')


def generate(assets):
    d=Diagram('01 / The shopping system','Three agents, one authoritative database, two separate vector collections.',1040)
    d.lane(24,105,1352,205,'CUSTOMER EXPERIENCE','The browser shares authenticated application state with the AI assistant.')
    d.node('browser',50,177,330,'Storefront + AI sidebar',['Page context · recently viewed IDs','Product cards · typed navigation'],'BROWSER')
    d.node('api',535,177,330,'FastAPI application',['Session + CSRF + customer identity','Conversation and safe action contracts'],'APPLICATION')
    d.node('customer',1020,177,330,'Customer agent',['Plans specialist calls · combines facts','Grounded reply + UI actions'],'COORDINATOR')
    d.edge('browser','api','message + page context','r','l',label_at=(458,218))
    d.edge('api','browser','reply + safe actions','l','r','response',offset_a=29,offset_b=29,label_at=(458,269))
    d.edge('api','customer','bound request','r','l',label_at=(942,218))
    d.edge('customer','api','answer + results','l','r','response',offset_a=29,offset_b=29,label_at=(942,269))
    d.lane(24,382,1352,229,'SPECIALISTS + MODEL','Every LLM role uses Ollama Cloud / gpt-oss:120b. Data access remains in validated tools.')
    d.node('retrieval',50,465,330,'Retrieval agent',['Rewrite / split → search → approve','Coverage → follow-up queries or done'],'PRODUCT DISCOVERY')
    d.node('cart',535,465,330,'Cart agent',['Resolve products · validate cart','Quotes · orders · shipping · reviews'],'SHOPPING OPERATIONS','write')
    d.node('memory',1020,465,330,'Conversation + memory',['SQL history + optional preferences','Owner / active / version rechecks'],'CUSTOMER CONTEXT','response')
    d.edge('customer','retrieval','retrieve products','b','t',via=((1110,341),(215,341)),offset_a=-75,label_at=(480,341))
    d.edge('customer','cart','manage cart','b','t',via=((1160,365),(700,365)),offset_a=-25,label_at=(840,365))
    d.edge('customer','memory','recall / approved preferences','b','t',label_at=(1185,420))
    d.lane(24,689,1352,277,'SHARED SERVICES + STORAGE','SQLite owns the facts; FTS and Qdrant support discovery. Inspect the detailed views for calls and return paths.')
    d.node('search',50,771,285,'Search + SQL tools',['30% BM25 + 70% vectors · top-3','SQL fields / filters / pagination'],'RETRIEVAL TOOLS')
    d.node('sql',388,771,285,'SQLite + FTS5',['Products · users · carts · orders','Nutrition · history · memory'],'AUTHORITATIVE STORE','write')
    d.node('vectors',726,771,285,'Qdrant collections',['market_products: product vectors','customer_memories: owner scoped'],'DERIVED INDEXES','sync')
    d.node('indexing',1064,771,285,'BGE + index jobs',['1024-dimensional query embeddings','Durable product / memory sync'],'EMBEDDING SERVICES','sync')
    d.edge('retrieval','search','search / select','b','t',via=((215,644),(192.5,644)),label_at=(180,655))
    d.edge('cart','sql','validate / transact','b','t','write',via=((700,664),(480.5,664)),offset_b=-50,label_at=(600,664))
    d.edge('memory','sql','read history / facts','b','t',via=((1185,632),(580.5,632)),offset_b=50,label_at=(960,632))
    d.edge('search','sql','read SQL facts','r','l',offset_a=-20,offset_b=-20)
    d.edge('sql','search','fresh SQL facts','l','r','response',offset_a=20,offset_b=20)
    d.edge('search','vectors','product vector query','b','b',via=((192.5,930),(868.5,930)),label_at=(540,930))
    d.edge('indexing','vectors','upsert / delete','l','r','sync')
    d.save(assets/'architecture.svg')

    d=Diagram('02 / Retrieval is an evidence loop','Hybrid discovery and SQL selection feed batched approval, then a bounded coverage check.',1160)
    d.lane(24,105,1352,205,'PLAN','Ollama rewrites the request and chooses hybrid, SQL or both. Product output is schema validated.')
    d.node('request',50,176,335,'Customer request',['Product question + known context','Expected facts / comparisons'],'INPUT')
    d.node('rewrite',535,176,335,'Rewrite + split',['Queries · sources · filters · fields','CatalogQuery / ProductEvidence schema'],'OLLAMA')
    d.node('tasks',1020,176,335,'Search task queue',['New subqueries + paginated selections','Round / search / duplicate limits'],'BOUNDED EXECUTION')
    d.edge('request','rewrite','request','r','l',label_at=(460,235));d.edge('rewrite','tasks','validated plan','r','l',label_at=(945,235))
    d.lane(24,385,1352,325,'RETRIEVE','Parallel candidate sources for hybrid ranking; structured SQL is also an independent selection path.')
    d.node('bm25',50,480,300,'BM25 / SQLite FTS5',['Lexical candidates + SQL filters','Names · descriptions · nutrition'],'30% KEYWORD')
    d.node('vector',395,480,300,'BGE → Qdrant query',['1024-d query · cosine candidates','market_products + payload filters'],'70% SEMANTIC','sync')
    d.node('sql',740,480,300,'Structured SQL selection',['Selected fields · category / price filters','All-match counts + pagination'],'SQL PATH','write')
    d.node('fusion',1085,480,270,'Merge + hydrate',['Normalize → weighted sum','Top-3 + fresh SQL product facts'],'HYBRID / SQL RESULTS')
    d.edge('tasks','bm25','hybrid query','b','t',via=((1090,345),(200,345)),offset_a=-97,label_at=(360,345))
    d.edge('tasks','vector','embed + query','b','t','sync',via=((1150,365),(545,365)),offset_a=-37,label_at=(655,365))
    d.edge('tasks','sql','SQL task','b','t','write',via=((1210,420),(890,420)),offset_a=23,label_at=(1090,420))
    d.edge('bm25','fusion','lexical candidates','b','b','response',via=((200,636),(1140,636)),offset_b=-80,label_at=(445,636))
    d.edge('vector','fusion','semantic candidates','b','b','response',via=((545,672),(1200,672)),offset_b=-20,label_at=(815,672))
    d.edge('sql','fusion','SQL rows','r','l','response',offset_a=-20,offset_b=-20)
    d.edge('fusion','sql','hydrate IDs','l','r',offset_a=25,offset_b=25)
    d.lane(24,791,1352,287,'APPROVE → CHECK → RETURN','Only approved products enter the evidence pool. Runtime evidence stays in memory, grouped under its query.')
    d.node('judge',50,869,335,'Batch relevance approval',['Ollama returns approved chunk IDs','Mapped to 0 / 1 for each chunk'],'OLLAMA')
    d.node('coverage',535,869,335,'Coverage validation',['Are the approved facts sufficient?','Missing needs → new subqueries'],'OLLAMA')
    d.node('output',1020,869,335,'Approved evidence groups',['Query / subquery + approved products','Complete flag + trace / limitations'],'RETURN TO CUSTOMER','response')
    d.edge('fusion','judge','retrieved chunks','b','t',via=((1280,745),(217.5,745)),offset_a=60,label_at=(770,745))
    d.edge('judge','coverage','approved pool','r','l',label_at=(460,930))
    d.edge('coverage','output','sufficient','r','l','response',label_at=(945,930))
    d.edge('coverage','tasks','missing → follow-up tasks','b','r',kind='request',via=((702.5,1110),(1388,1110),(1388,236)),label_at=(1090,1110))
    d.save(assets/'architecture-retrieval.svg')

    d=Diagram('03 / From a shopping request to a real order','Cart changes use customer-bound tools. Checkout confirmation comes from the customer’s actual form.',1010)
    d.lane(24,105,1352,220,'AGENT-ASSISTED SHOPPING','The coordinator supplies approved product evidence and history to the cart specialist.')
    d.node('customer',50,190,335,'Customer coordinator',['Request + product references','Customer identity bound by application'],'ORCHESTRATION')
    d.node('cart',535,190,335,'Cart agent + tools',['Resolve / add / change / remove','Inspect cart · order history · reviews'],'VALIDATED TOOL CALLS','write')
    d.node('sql',1020,190,335,'SQL cart service',['Check product, quantity, stock, price','Shared cart revision + dollar totals'],'CUSTOMER-SCOPED STATE','write')
    d.edge('customer','cart','shopping intent','r','l',label_at=(460,245));d.edge('cart','sql','validated operation','r','l','write',label_at=(945,245))
    d.lane(24,404,1352,221,'QUOTE + EXPLICIT CONFIRMATION','The model can prepare a quote. It cannot supply the trusted customer confirmation.')
    d.node('quote',1020,480,335,'Checkout quote',['Snapshot + expiry + opaque token','Changed stock / price → quote again'],'PREPARE')
    d.node('form',535,480,335,'Browser confirmation form',['Delivery address + COD choice','Customer explicitly confirms order'],'CUSTOMER ACTION','write')
    d.node('checkout',50,480,335,'Confirmed checkout API',['Session + CSRF + quote ownership','Validate snapshot and confirmation'],'TRUSTED APPLICATION','write')
    d.edge('sql','quote','prepare quote','b','t',label_at=(1185,368))
    d.edge('quote','form','quoted items + total','l','r','response',label_at=(945,540))
    d.edge('form','checkout','confirmed form','l','r','write',label_at=(460,540))
    d.lane(24,712,1352,222,'ATOMIC ORDER + RECEIPT','Cash on delivery remains unpaid. Pending means awaiting fulfillment; carrier/payment integrations are not connected.')
    d.node('transaction',50,790,335,'SQLite transaction',['Insert order + deduct stock once','Clear cart · bind quote to order'],'ATOMIC / IDEMPOTENT','write')
    d.node('receipt',535,790,335,'Order + updated cart',['Receipt + purchased line items','Repeated token → same order'],'API RESPONSE','response')
    d.node('browser',1020,790,335,'Storefront + order history',['Render receipt · refresh shared cart','Owned orders / shipping / reviews'],'CUSTOMER EXPERIENCE','response')
    d.edge('checkout','transaction','commit validated order','b','t','write',label_at=(217,677))
    d.edge('transaction','receipt','committed result','r','l','response',label_at=(460,848))
    d.edge('receipt','browser','receipt + cart refresh','r','l','response',label_at=(945,848))
    d.save(assets/'architecture-ordering.svg')

    d=Diagram('04 / Private memory across conversations','Conversation history lives in SQL. Optional long-term preferences have a separate derived vector index.',1040)
    d.lane(24,105,1352,211,'RECALL','The authenticated person_id scopes recall. Vectors alone are never trusted to establish ownership or freshness.')
    d.node('chat',50,180,335,'Authenticated chat',['Current page + request + history','Memory enabled by customer preference'],'CUSTOMER CONTEXT')
    d.node('query',535,180,335,'BGE → memory recall',['Embed request · owner filter','Owner + model filter · SQL recheck'],'SEMANTIC RECALL','sync')
    d.node('vectors',1020,180,335,'Qdrant memory collection',['customer_memories only','memory_id / person_id / version'],'DERIVED INDEX','sync')
    d.edge('chat','query','recall request','r','l',label_at=(460,236));d.edge('query','vectors','filtered vector query','r','l','sync',label_at=(945,236))
    d.lane(24,405,1352,211,'VERIFY + RESPOND','A SQL recheck removes deleted, changed, foreign-owner and inactive facts before they enter the prompt.')
    d.node('sql',1020,480,335,'Authoritative SQL recheck',['Owner · active · current version','Chat history stored independently'],'SQL GUARD','write')
    d.node('context',535,480,335,'Verified customer context',['Bounded history + approved memory','Page registry + available operations'],'PROMPT CONTEXT')
    d.node('customer',50,480,335,'Customer coordinator',['Plan with verified preferences','Grounded reply + typed UI actions'],'OLLAMA')
    d.edge('vectors','sql','candidate IDs / versions','b','t','response',label_at=(1187,366))
    d.edge('sql','context','verified facts + history','l','r','response',label_at=(945,537))
    d.edge('context','customer','bounded prompt','l','r',label_at=(460,537))
    d.lane(24,715,1352,233,'SAVE / EDIT / DELETE','Approved explicit preferences are stored in SQL first. Queued synchronization is separate from product indexing.')
    d.node('facts',50,799,335,'Approved preference changes',['Explicit facts / customer settings','Disable or delete memory controls'],'CUSTOMER-OWNED')
    d.node('save',535,799,335,'SQL facts + sync queue',['Save / version / revoke immediately','Retries without trusting stale vectors'],'AUTHORITATIVE WRITE','write')
    d.node('sync',1020,799,335,'BGE + memory sync',['Encode current memory document','Upsert / delete customer_memories'],'DERIVED WRITE','sync')
    d.edge('facts','save','validated preference','r','l','write',label_at=(460,859));d.edge('save','sync','durable job','r','l','sync',label_at=(945,859))
    d.edge('sync','vectors','upsert / delete vectors','r','t','sync',via=((1388,859),(1388,96),(1187.5,96)),label_at=(1230,96))
    d.save(assets/'architecture-memory.svg')

    d=Diagram('05 / One catalog, two search indexes','SQL product_id and category_id are shared with the product vector payload. New products begin in SQL.',1000)
    d.lane(24,105,1352,221,'CATALOG WRITE','Seed / import / product changes go through SQL. Prices, stock and nutrition are authoritative here.')
    d.node('input',50,190,335,'Catalog input',['Product details + image references','Create / update / delete'],'PRODUCT DATA')
    d.node('sql',535,190,335,'SQLite product catalog',['Stable product_id + category_id','Search revision + nutrition facts'],'AUTHORITATIVE STORE','write')
    d.node('fts',1020,190,335,'FTS5 / BM25 index',['SQL triggers maintain search text','Synchronized in catalog transaction'],'LEXICAL INDEX','write')
    d.edge('input','sql','catalog transaction','r','l','write',label_at=(460,247));d.edge('sql','fts','SQL triggers','r','l','write',label_at=(945,247))
    d.lane(24,405,1352,220,'DURABLE PRODUCT INDEXING','The indexing command processes queued jobs; failures retry and reconciliation repairs stale / orphan vectors.')
    d.node('jobs',535,480,335,'product_index_jobs',['Product ID + revision + operation','Pending → processing → done / failed'],'DURABLE QUEUE','sync')
    d.node('document',50,480,335,'Current product document',['Read latest SQL product fields','Name / category / description / kcal'],'INDEXING PROCESS')
    d.node('bge',1020,480,335,'BGE embeddings',['BAAI/bge-large-en-v1.5','1024-dimensional product vectors'],'LOCAL MODEL','sync')
    d.edge('sql','jobs','enqueue product revision','b','t','sync',label_at=(702,370))
    d.edge('jobs','document','load current document','l','r',label_at=(460,537))
    d.edge('document','bge','encode product text','b','l','sync',via=((217.5,664),(990,664),(990,540)),label_at=(700,664))
    d.lane(24,727,1352,199,'VECTOR WRITE + QUERY CONSISTENCY','Search hydrates current SQL facts; stale prices and stock are never taken as authoritative from vector payloads.')
    d.node('query',50,793,335,'Hybrid search at query time',['Query BGE + BM25 candidates','Weighted ranking → fresh SQL facts'],'READ PATH')
    d.node('vectors',1020,793,335,'Qdrant market_products',['Point ID = SQL product_id','Category ID / model / hash / revision'],'DERIVED PRODUCT INDEX','sync')
    d.node('status',535,793,335,'Job result + reconciliation',['Mark completion / retry failures','Compare revisions / remove orphans'],'INDEXING STATUS','sync')
    d.edge('bge','vectors','upsert / delete point','b','t','sync',label_at=(1187,710))
    d.edge('vectors','status','operation result','l','r','response',label_at=(945,850))
    d.edge('query','vectors','embedded query','b','b',via=((217.5,952),(1187.5,952)),label_at=(700,952))
    d.save(assets/'architecture-indexing.svg')
