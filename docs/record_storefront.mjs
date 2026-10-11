import './browser-platform.mjs';
const { chromium } = await import('playwright');
import { writeFile } from 'node:fs/promises';
import { randomBytes } from 'node:crypto';
import { performance } from 'node:perf_hooks';
const args=process.argv.slice(2);
const option=name=>args[args.indexOf(name)+1];
const base=option('--url'), output=option('--output'), manifest=option('--manifest');
if(!args.includes('--check-browser') && (!base || !output || !manifest))throw new Error('Launch through python docs/record_storefront.py for isolated data');
let browser;
try { browser=await chromium.launch({headless:!args.includes('--headed'),slowMo:100}); }
catch(error) {
  console.error('Chromium could not launch. Run: npm --prefix docs run install-browser');
  console.error('If Linux libraries are missing: npm --prefix docs run install-browser -- --with-deps');
  console.error(error.message);process.exit(1);
}
if(args.includes('--check-browser')){await browser.close();console.log('Chromium launch preflight passed.');process.exit(0);}
const context=await browser.newContext({viewport:{width:1440,height:900},recordVideo:{dir:output,size:{width:1440,height:900}}});
const page=await context.newPage();const video=page.video();const began=performance.now();
const elapsed=()=>(performance.now()-began)/1000;
const cuts=[];let finished=false;let purchased=[];
async function read(seconds=3){await page.waitForTimeout(seconds*1000);}
async function click(locator){await locator.scrollIntoViewIfNeeded();const box=await locator.boundingBox();if(box)await page.mouse.move(box.x+box.width/2,box.y+box.height/2,{steps:20});await locator.click();}
async function enter(locator,value){await click(locator);await locator.pressSequentially(value,{delay:140});await read(1);}
async function closeProduct(){if(await page.locator('#detailOverlay.open').count())await click(page.locator('.detail-close'));}
async function ask(query){
  console.log(`Shopping: ${query}`);
  await click(page.locator('#chatInput'));await page.locator('#chatInput').pressSequentially(query,{delay:45});
  const pending=page.waitForResponse(r=>r.url()===base+'/api/chat' && r.request().method()==='POST',{timeout:240000});
  await page.locator('#chatInput').press('Enter');const start=elapsed();const response=await pending;
  if(!response.ok())throw new Error(`Live chat failed with HTTP ${response.status()}; no reply is replaced or fabricated`);
  const result=await response.json();const end=elapsed();
  if(end-start>6)cuts.push({start:start+2,end:end-.5});
  await page.locator('#chatSend').waitFor({state:'visible'});
  await page.waitForFunction(()=>!document.getElementById('chatSend').disabled,{timeout:30000});
  await read(Math.min(12,Math.max(5,(result.answer?.length||0)/75)));return result;
}
try{
  await page.goto(base,{waitUntil:'networkidle'});await page.locator('#products .prod-card').first().waitFor({timeout:30000});await read(3);
  console.log('Creating demo account at a readable pace.');
  const password=randomBytes(10).toString('hex');
  await click(page.locator('#authArea button'));await read(2);
  await enter(page.locator('#first_name'),'Demo');await enter(page.locator('#last_name'),'Shopper');
  await enter(page.locator('#email'),'tour@example.com');await enter(page.locator('#password'),password);await read(3);
  const registered=page.waitForResponse(r=>r.url()===base+'/api/register' && r.request().method()==='POST');
  await click(page.locator('#registerForm button[type=submit]'));
  const registration=await registered;
  if(!registration.ok()){
    const details=await registration.json().catch(()=>({}));
    const fields=Array.isArray(details.detail)?details.detail.map(e=>`${(e.loc||[]).join('.')}: ${e.type}`).join(', '):'See registration form message';
    throw new Error(`Demo registration failed: HTTP ${registration.status()} (${fields})`);
  }
  await page.waitForFunction(()=>document.getElementById('authArea').textContent.includes('Demo'));await read(5);
  console.log('Showing sign-out and sign-in through the actual forms.');
  const signedOut=page.waitForResponse(r=>r.url()===base+'/api/logout' && r.request().method()==='POST');
  await click(page.getByRole('button',{name:'Sign out',exact:true}));if(!(await signedOut).ok())throw new Error('Sign out failed');
  await page.getByRole('button',{name:'Register / Sign in',exact:true}).waitFor();
  await click(page.getByRole('button',{name:'Register / Sign in',exact:true}));await click(page.locator('#tabLogin'));await read(2);
  await enter(page.locator('#login_email'),'tour@example.com');await enter(page.locator('#login_password'),password);await read(3);
  const signedIn=page.waitForResponse(r=>r.url()===base+'/api/login' && r.request().method()==='POST');
  await click(page.locator('#loginForm button[type=submit]'));if(!(await signedIn).ok())throw new Error('Sign in failed');
  await page.waitForFunction(()=>document.getElementById('authArea').textContent.includes('Demo'));await read(5);
  await page.mouse.wheel(0,450);await read(3);
  await click(page.locator('#assistantTab'));
  await ask('Hi! I am shopping for breakfast and some snacks today.');
  const basket=[
    {name:'Apples 1kg',research:'Compare apples and apple juice: what are their prices and estimated calories?'},
    {name:'Lipton Yellow Label Tea',research:'Tell me about Lipton Yellow Label Tea. What is the package size and price?'},
    {name:'Whole Wheat Bread',research:'Compare whole wheat bread and white sandwich bread. Which costs less, and what are their recorded calories?'},
    {name:'Greek Yogurt',research:'What size is the Greek Yogurt, how much does it cost and what are its estimated calories?'},
    {name:'Mixed Nuts 500g',research:'I want a snack under $6. Compare Mixed Nuts 500g and Potato Chips Salted by price and estimated calories.'}
  ];
  for(const product of basket){
    await closeProduct();await ask(product.research);
    await ask(`Show me ${product.name} please.`);
    await page.locator('#detailOverlay.open').waitFor({timeout:15000});
    if(!(await page.locator('#detailContent').innerText()).includes(product.name))throw new Error(`The requested product did not open: ${product.name}`);
    await read(4);await ask('Add it to my cart.');
    const response=await page.request.get(base+'/api/cart');const cart=await response.json();
    if(!response.ok() || !cart.items?.some(p=>p.name===product.name && p.quantity===1))throw new Error(`The live agent did not add ${product.name}`);
  }
  await closeProduct();await ask('Change the Apples 1kg quantity to 2.');
  let response=await page.request.get(base+'/api/cart');let cart=await response.json();
  if(!response.ok() || cart.items.length!==5 || !cart.items.some(p=>p.name==='Apples 1kg' && p.quantity===2))throw new Error('Expected five distinct products and two apples in the actual cart');
  await ask('Show my cart.');await page.locator('#cartPage').waitFor({state:'visible'});await read(5);
  const summary=await ask('What are the quantities, prices and total for the five products in this cart?');
  if(/(?:would you like|can i|do you want)[^.!?]*\b(?:view|show|open|see)\b[^.!?]*\bcart\b/i.test(summary.answer||''))throw new Error('The assistant offered to open a cart that is already visible');
  await ask('I want to checkout my cart.');
  await click(page.getByRole('button',{name:'Review and confirm checkout',exact:true}).last());
  await page.locator('.checkout-confirmation').waitFor();await page.locator('.checkout-confirmation textarea[name=address]').pressSequentially('123 Demo Street, Example City',{delay:50});
  await page.locator('.checkout-confirmation input[name=confirmed]').check();await read(2);
  const ordered=page.waitForResponse(r=>r.url()===base+'/api/cart/checkout' && r.request().method()==='POST');
  await click(page.locator('.checkout-confirmation button[type=submit]'));const orderResponse=await ordered;if(!orderResponse.ok())throw new Error('Actual checkout failed');
  const receipt=await orderResponse.json();purchased=receipt.order?.items?.map(p=>p.name)||[];
  if(purchased.length!==5 || !basket.every(p=>purchased.includes(p.name)))throw new Error('The confirmed order must contain all five chosen products');
  await page.locator('#ordersContent .order-card').first().waitFor();await read(5);
  await ask('Show my previous orders and the products I just bought.');
  await click(page.locator('.page-nav button').filter({hasText:/^Profile$/}));await page.locator('#profilePage').waitFor({state:'visible'});await read(3);
  await click(page.locator('.page-nav button').filter({hasText:/^Settings$/}));await page.locator('#settingsContent input[type=checkbox]').waitFor();await read(4);
  await click(page.locator('.page-nav button').filter({hasText:/^Shop$/}));await read(3);finished=true;
}finally{
  await context.close();const recorded=await video.path();await browser.close();
  await writeFile(manifest,JSON.stringify({completed:finished,video:recorded,waiting_cuts:cuts,purchased_products:purchased},null,2)+'\n');
}
