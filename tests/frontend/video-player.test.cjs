const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function setup() {
 const elements={};
 for(const id of ['tourVideo','videoSection','videoFullscreen','fullscreenStatus','videoPlay','videoAvailability','recordingPending']) elements[id]={hidden:false,listeners:{},style:{},textContent:'',classList:{add(){},remove(){}},setAttribute(){},focus(){},addEventListener(key,fn){this.listeners[key]=fn;}};
 elements.tourVideo.play=async()=>{elements.tourVideo.listeners.play();};
 const document={getElementById:id=>elements[id],body:{style:{}},addEventListener(){},fullscreenEnabled:false};
 vm.runInNewContext(fs.readFileSync('docs/video-player.js','utf8'),{document,fetch:async()=>({ok:true})});
 return elements;
}
test('left play control starts actual video and returns on pause or end',async()=>{
 const e=setup();await e.videoPlay.listeners.click();assert.equal(e.videoPlay.hidden,true);
 e.tourVideo.listeners.pause();assert.equal(e.videoPlay.hidden,false);
 await e.videoPlay.listeners.click();e.tourVideo.listeners.ended();assert.equal(e.videoPlay.hidden,false);
});
test('failed playback keeps native/direct controls available with an explanation',async()=>{
 const e=setup();e.tourVideo.play=async()=>{throw Error('blocked');};await e.videoPlay.listeners.click();
 assert.match(e.videoAvailability.textContent,/native video controls/);assert.equal(e.videoPlay.hidden,false);
});
