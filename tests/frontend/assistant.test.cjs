const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor(tag='div') { this.tagName=tag.toUpperCase();this.children=[];this.value='';this._text='';this.hidden=true;this.style={};this.attributes={};this.classList={toggle(){}};this.scrollTop=0; }
  get textContent() { return this._text + this.children.map(c => c.textContent || '').join(''); }
  set textContent(value) { this._text=value;this.children=[]; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this._text='';this.children=items; }
  setAttribute(name,value) { this.attributes[name]=value; }
  focus() {}
  getBoundingClientRect() { return {top:this.top || 0}; }
  scrollTo(options) { this.lastScroll=options;this.scrollTop=options.top; }
}
const buttons = node => node.children.filter(child => child.tagName === 'BUTTON');
async function browser() {
  const elements=new Map(), calls=[], storage=new Map();
  const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const context=vm.createContext({console, innerWidth:1200,confirm:()=>true,
    document:{getElementById:get,createElement:tag=>new Element(tag),createTextNode:text=>({textContent:text}),body:new Element(),documentElement:{style:{setProperty(){}}}},
    sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    currentUser:{person_id:1},cart:[],selectedProductId:null,visibleProductIds:[3,4],activeCategory:1,activeSearch:'tea',
    showToast(){},renderAuthArea(){},updateCartBadge(){},renderCart(){},openModal(){},switchTab(){},escapeHTML:String,formatMoney:String,formatCalories:p=>p.calories_per_100==null?'':`${p.calories_per_100} kcal`,
    closeDetail(){context.selectedProductId=null;},async showProductDetail(id){context.selectedProductId=id;},async loadProducts(){},
    async apiRequest(path,options){calls.push({path,options});if(path==='/api/me')return {person_id:1};if(path==='/api/cart')return {items:[]};if(path==='/api/preferences')return {memory_enabled:true};if(path==='/api/memories')return [];if(path==='/api/chat')return context.chatResponse;throw Error('Unexpected '+path);},
    chatResponse:{answer:'<script>unsafe</script>',conversation_id:'conversation',results:{},actions:[],memory_status:{saved:0,sync:{failed:0}}}
  });
  vm.runInContext(fs.readFileSync('UI/frontend/js/markdown.js','utf8'),context);
  vm.runInContext(fs.readFileSync('UI/frontend/js/assistant.js','utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  return {context,get,calls,storage,run:code=>vm.runInContext(code,context)};
}

test('assistant opens and sends bounded structured page context, rendering model prose as text',async()=>{
  const b=await browser();b.get('assistantTab').onclick();
  assert.equal(b.get('assistantPanel').hidden,false);
  b.context.selectedProductId=3;b.get('chatInput').value='What about this tea?';
  await b.get('chatForm').onsubmit({preventDefault(){}});
  const request=b.calls.find(c=>c.path==='/api/chat');
  assert.equal(request.options.body.page_context.page,'product');
  assert.equal(request.options.body.page_context.product_id,3);
  assert.equal(request.options.body.person_id,undefined);
  assert.equal(b.get('chatMessages').children.at(-1).textContent,'<script>unsafe</script>');
  assert.equal(b.storage.get('market_conversation_1'),'conversation');
});

test('navigation allowlist rejects arbitrary pages and scripts',async()=>{
  const b=await browser();await b.run("executeAction({action:'navigate',page:'https://evil.test'})");
  assert.equal(b.run('currentPage'),'shop');
  await b.run("executeAction({action:'execute',query:'alert(1)'})");
  assert.equal(b.run('currentPage'),'shop');
  await b.run("executeAction({action:'navigate',page:'cart'})");
  assert.equal(b.run('currentPage'),'cart');
});

test('response from an earlier signed-in customer is discarded',async()=>{
  const b=await browser();let resolveReply;
  const original=b.context.apiRequest;
  b.context.apiRequest=(path,options)=>path==='/api/chat'?new Promise(resolve=>{resolveReply=resolve;}):original(path,options);
  b.get('chatInput').value='My cart';const pending=b.get('chatForm').onsubmit({preventDefault(){}});
  b.run('resetAssistant()');b.context.currentUser={person_id:2};
  const count=b.get('chatMessages').children.length;
  resolveReply(b.context.chatResponse);await pending;
  assert.equal(b.get('chatMessages').children.length,count);
  assert.equal(b.run('conversationId'),null);
  assert.equal(b.storage.get('market_conversation_2'),undefined);
});

test('follow-up carries shown product IDs and automatically opens the requested product',async()=>{
  const b=await browser();
  b.context.chatResponse={answer:'Here is tea.',conversation_id:'conversation',actions:[],results:{retrieval:{sections:[{chunks:[{approval:1,product:{product_id:3,name:'Tea',price:4}}]}]}}};
  b.context.knownProducts=new Map();b.context.addToCart=()=>{};
  b.get('chatInput').value='Where can I find tea?';await b.get('chatForm').onsubmit({preventDefault(){}});
  b.context.chatResponse={answer:'Opening tea.',conversation_id:'conversation',actions:[{action:'open_product',product_id:3}],results:{}};
  b.get('chatInput').value='Show it to me';await b.get('chatForm').onsubmit({preventDefault(){}});
  const requests=b.calls.filter(c=>c.path==='/api/chat');
  assert.deepEqual(Array.from(requests[1].options.body.page_context.referenced_product_ids),[3]);
  assert.equal(b.context.selectedProductId,3);
});

test('cart refresh failure does not prevent a successful product-opening action',async()=>{
  const b=await browser();const original=b.context.apiRequest;
  b.context.apiRequest=(path,options)=>path==='/api/cart'?Promise.reject(Error('unavailable')):original(path,options);
  b.context.chatResponse={answer:'Opening tea.',conversation_id:'conversation',actions:[{action:'open_product',product_id:3}],results:{}};
  b.get('chatInput').value='Show tea';await b.get('chatForm').onsubmit({preventDefault(){}});
  assert.equal(b.context.selectedProductId,3);
});

test('Enter submits once while Shift+Enter and composition preserve input',async()=>{
  const b=await browser();let submissions=0;
  b.get('chatForm').requestSubmit=()=>{submissions++;};
  const press=overrides=>{let prevented=false;b.get('chatInput').onkeydown({key:'Enter',shiftKey:false,isComposing:false,repeat:false,preventDefault(){prevented=true;},...overrides});return prevented;};
  assert.equal(press({}),true);assert.equal(submissions,1);
  assert.equal(press({shiftKey:true}),false);assert.equal(submissions,1);
  assert.equal(press({isComposing:true}),false);assert.equal(submissions,1);
  assert.equal(press({repeat:true}),true);assert.equal(submissions,1);
  b.run('chatBusy=true');assert.equal(press({}),true);assert.equal(submissions,1);
});

test('product opens before a slow cart refresh finishes',async()=>{
  const b=await browser();const original=b.context.apiRequest;let finishCart;
  b.context.apiRequest=(path,options)=>path==='/api/cart'?new Promise(resolve=>{finishCart=resolve;}):original(path,options);
  b.context.chatResponse={answer:'Opening Toast Bread.',conversation_id:'conversation',actions:[{action:'open_product',product_id:4}],results:{}};
  b.get('chatInput').value='Show toast bread';const pending=b.get('chatForm').onsubmit({preventDefault(){}});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(b.context.selectedProductId,4);
  assert.equal(buttons(b.get('chatMessages').children.at(-1)).length,0); // Product is already open.
  finishCart({items:[]});await pending;
});

test('successful add refreshes shared cart but View cart remains optional',async()=>{
  const b=await browser();const original=b.context.apiRequest;
  b.context.apiRequest=(path,options)=>path==='/api/cart'?Promise.resolve({items:[{product_id:4,quantity:1}]}):original(path,options);
  b.context.chatResponse={answer:'Added Toast Bread.',conversation_id:'conversation',actions:[{action:'navigate',page:'cart',trigger:'on_click'},{action:'refresh_cart'}],results:{}};
  b.get('chatInput').value='Add toast bread';await b.get('chatForm').onsubmit({preventDefault(){}});
  assert.equal(b.run('currentPage'),'shop');assert.equal(b.context.cart[0].quantity,1);
  const choices=buttons(b.get('chatMessages').children.at(-1));
  assert.equal(choices.length,1);assert.equal(choices[0].textContent,'View cart');
  await choices[0].onclick();assert.equal(b.run('currentPage'),'cart');
});

test('optional product suggestion waits for a click while explicit viewing opens directly',async()=>{
  const b=await browser();
  b.context.chatResponse={answer:'Would you like to view the tea?',conversation_id:'conversation',actions:[{action:'open_product',product_id:3,trigger:'on_click'}],results:{}};
  b.get('chatInput').value='Tell me about tea';await b.get('chatForm').onsubmit({preventDefault(){}});
  assert.equal(b.context.selectedProductId,null);
  await buttons(b.get('chatMessages').children.at(-1))[0].onclick();
  assert.equal(b.context.selectedProductId,3);
});

function descendants(node,tag) {
  return node.children.flatMap(child => child.children ? [...(child.tagName===tag.toUpperCase()?[child]:[]),...descendants(child,tag)] : []);
}

test('assistant Markdown formats bold and lists while HTML and unsafe links stay text',async()=>{
  const b=await browser();const parent=new Element();b.context.target=parent;
  b.context.markdown='Available: **Potato Chips Salted**\n\n- Price: $2.49\n- Stock: 140\n\n<script>alert(1)</script> [bad](javascript:alert)\n\n```\n<img src=x onerror=alert(1)>\n```';
  b.run('renderChatMarkdown(target,markdown)');
  assert.equal(descendants(parent,'strong')[0].textContent,'Potato Chips Salted');
  assert.equal(descendants(parent,'li').length,2);
  assert.equal(descendants(parent,'script').length,0);assert.equal(descendants(parent,'img').length,0);
  assert.equal(descendants(parent,'a').length,0);
  assert.match(parent.textContent,/<script>alert\(1\)<\/script>/);
  assert.equal(descendants(parent,'code')[0].textContent,'<img src=x onerror=alert(1)>');
});

test('scroll focuses start of answer inside pane without scrolling document',async()=>{
  const b=await browser(), pane=b.get('chatMessages'), answer=new Element();pane.top=80;pane.scrollTop=200;answer.top=330;b.context.target=answer;
  b.run('focusChatAnswer(messages,target)');assert.equal(pane.lastScroll.top,432);
});

test('a product card and matching action offer only one View button',async()=>{
  const b=await browser();b.context.knownProducts=new Map();b.context.addToCart=()=>{};
  b.context.chatResponse={answer:'Here is tea.',conversation_id:'conversation',actions:[{action:'open_product',product_id:3,trigger:'on_click'}],results:{retrieval:{sections:[{chunks:[{approval:1,product:{product_id:3,name:'Tea',price:4}}]}]}}};
  b.get('chatInput').value='Tell me about tea';await b.get('chatForm').onsubmit({preventDefault(){}});
  assert.equal(descendants(b.get('chatMessages').children.at(-1),'button').filter(button=>button.textContent.startsWith('View product')).length,1);
});

test('already open cart and product do not get redundant navigation buttons',async()=>{
  const b=await browser();b.run("currentPage='cart'");
  b.context.chatResponse={answer:'Your cart is updated.',conversation_id:'conversation',actions:[{action:'navigate',page:'cart',trigger:'on_click'}],results:{}};
  b.get('chatInput').value='Add tea';await b.get('chatForm').onsubmit({preventDefault(){}});
  assert.equal(buttons(b.get('chatMessages').children.at(-1)).length,0);
  b.context.selectedProductId=3;b.context.knownProducts=new Map();b.context.addToCart=()=>{};
  b.context.chatResponse={answer:'Tea details.',conversation_id:'conversation',actions:[{action:'open_product',product_id:3,trigger:'on_click'}],results:{retrieval:{sections:[{chunks:[{approval:1,product:{product_id:3,name:'Tea',price:4}}]}]}}};
  b.get('chatInput').value='Tell me more';await b.get('chatForm').onsubmit({preventDefault(){}});
  assert.equal(descendants(b.get('chatMessages').children.at(-1),'button').filter(button=>button.textContent.startsWith('View product')).length,0);
});

test('shared calorie formatter preserves zero values, units and estimate labels',()=>{
  const context=vm.createContext({});vm.runInContext(fs.readFileSync('UI/frontend/js/api.js','utf8'),context);
  const format=vm.runInContext('formatCalories',context);
  assert.equal(format({calories_per_100:0,calorie_basis:'per_100ml',calorie_status:'estimated'}),'Estimated calories: 0 kcal per 100 ml');
  assert.equal(format({calories_per_100:194,calorie_basis:'per_100g',calorie_status:'estimated'}),'Estimated calories: 194 kcal per 100 g');
  assert.equal(format({calories_per_100:50,calorie_basis:'per_100g',calorie_status:'label_verified'}),'Calories: 50 kcal per 100 g');
  assert.equal(format({calories_per_100:null}),'');
});

test('context-only product choices have working View buttons without retrieval',async()=>{
  const b=await browser();b.context.knownProducts=new Map();b.context.addToCart=()=>{};
  b.context.chatResponse={answer:'Which apple product?',conversation_id:'conversation',actions:[],results:{},products:[
    {product_id:29,name:'Apples 1kg',price:3.99},{product_id:34,name:'Apple Juice 1L',price:2.29}]};
  b.get('chatInput').value='Show it';await b.get('chatForm').onsubmit({preventDefault(){}});
  const reply=b.get('chatMessages').children.at(-1),cards=reply.children.filter(c=>c.className==='assistant-product');
  assert.equal(cards.length,2);
  assert.equal(buttons(cards[0])[0].textContent,'View product');
  assert.equal(buttons(cards[1])[0].textContent,'View product');
  await buttons(cards[0])[0].onclick();assert.equal(b.context.selectedProductId,29);
  await buttons(cards[1])[0].onclick();assert.equal(b.context.selectedProductId,34);
  assert.deepEqual(Array.from(b.run('recentProductIds')),[29,34]);
});

test('server cards and retrieval evidence for the same product render one fresh card',async()=>{
  const b=await browser();
  const list=b.run(`chatProducts({products:[{product_id:29,name:'Apples',price:3.99}],results:{retrieval:{sections:[{chunks:[{approval:1,product:{product_id:29,name:'Apples',price:1}}]}]}}})`);
  assert.equal(list.length,1);assert.equal(list[0].price,3.99);
});
