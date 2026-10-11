const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function setup(reduced = false) {
  class Element {
    constructor(id) { this.id=id; this.attrs={}; this.listeners={}; this.children=[]; this.textContent=''; }
    setAttribute(key,value) { this.attrs[key]=value; }
    addEventListener(key,fn) { this.listeners[key]=fn; }
    replaceChildren() { this.children=[]; }
    appendChild(child) { this.children.push(child); }
    focus() { this.focused=true; }
  }
  const ids=['map','motion','diagramPanel','openDiagram','storyLabel','storyTitle','storyDescription','storySteps','detail'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element(id)]));
  const tabs=['overview','retrieval','ordering','memory','indexing'].map((key,i)=>{const el=new Element('tab-'+key);el.dataset={view:key};el.textContent=`0${i+1} ${key}`;return el;});
  const svg={tagName:'svg',pauseAnimations(){this.paused=true;},unpauseAnimations(){this.paused=false;}};
  const node=new Element('node');node.dataset={detail:'Owned SQL facts are authoritative.'};
  elements.map.contentDocument={documentElement:svg,querySelectorAll(){return [node];}};
  vm.runInNewContext(fs.readFileSync('docs/architecture.js','utf8'),{document:{getElementById:id=>elements[id],querySelectorAll:()=>tabs,createElement:()=>new Element()},matchMedia:()=>({matches:reduced})});
  return {elements,tabs,svg,node};
}
test('architecture workflow selection updates diagram, narrative and keyboard tab state',()=>{
  const {elements,tabs}=setup();tabs[1].listeners.click();
  assert.equal(elements.map.attrs.data,'assets/architecture-retrieval.svg');
  assert.equal(elements.diagramPanel.attrs['aria-labelledby'],'tab-retrieval');
  assert.equal(tabs[1].attrs['aria-selected'],'true');
  assert.equal(elements.storySteps.children.length,4);
  tabs[1].listeners.keydown({key:'End',preventDefault(){}});
  assert.equal(elements.map.attrs.data,'assets/architecture-indexing.svg');
  assert.equal(tabs[4].focused,true);
  assert.equal(tabs[1].tabIndex,-1);
});
test('animation pause survives workflow reload and reduced motion; nodes remain inspectable',()=>{
  const {elements,tabs,svg,node}=setup(true);assert.equal(svg.paused,true);
  tabs[3].listeners.click();elements.map.listeners.load();assert.equal(svg.paused,true);
  node.listeners.focus();assert.equal(elements.detail.textContent,node.dataset.detail);
  elements.motion.listeners.click();assert.equal(svg.paused,false);
  assert.equal(elements.motion.attrs['aria-pressed'],'false');
});
