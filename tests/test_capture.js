// The final data event fires AFTER state becomes inactive, but BEFORE the stop event.
// Rotation must not erase a clip's container while finishClip awaits that stop event.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
function runtime() {
  const elements = new Map();
  class Recorder {
    static isTypeSupported() { return true; }
    constructor() { this.state = 'inactive'; this.mimeType = 'video/webm'; }
    start() { this.state = 'recording'; }
    stop() {
      this.state = 'inactive';
      queueMicrotask(() => { this.ondataavailable({data:new Blob(['tail'])}); this.onstop(); });
    }
  }
  const context = vm.createContext({
    Blob, URLSearchParams, URL, MediaRecorder:Recorder, queueMicrotask,
    performance:{now:()=>100000}, location:{search:'',href:'http://localhost/playtest'},
    localStorage:{getItem:()=>null}, navigator:{mediaDevices:{getDisplayMedia:()=>{}}},
    window:{MediaRecorder:Recorder,addEventListener:()=>{}},
    document:{getElementById:(id)=>{if(!elements.has(id)) elements.set(id,{value:'',textContent:'',addEventListener:()=>{}});return elements.get(id);},addEventListener:()=>{}},
    fetch:()=>new Promise(()=>{}),
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../mac/desk-ui/playtest.js'),'utf8'),context);
  return context;
}
test('rotation keeps a complete clip through the asynchronous final data event',async()=>{
  const context=runtime();
  const size=await vm.runInContext(`(async()=>{
    session={stream:{},buffers:[],ending:false};
    const b=newBuffer(session);
    b.recorder.ondataavailable({data:new Blob(['header'])});
    const result=await stopBuffer(b,true);
    return result.size;
  })()`,context);
  assert.equal(size,10); // header + tail, rather than an empty/partial container
});
test('idle rotation retires stale buffers and retains a pinned observation',async()=>{
  const context=runtime();
  const result=vm.runInContext(`(()=>{
    session={stream:{},buffers:[],ending:false};
    const old=newBuffer(session);old.start=0;
    const pinned=newBuffer(session);pinned.start=5;clip={buffer:pinned};
    maintainBuffers(session);
    return {old:old.recorder.state,pinned:pinned.recorder.state,count:session.buffers.length,latest:session.buffers.at(-1).start};
  })()`,context);
  assert.equal(result.old,'inactive');assert.equal(result.pinned,'recording');assert.equal(result.count,2);assert.equal(result.latest,100);
});
