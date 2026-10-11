const {JSDOM}=require('jsdom'),fs=require('fs'),assert=require('node:assert/strict');
const root=require('node:path').resolve(__dirname,'..');
const html=fs.readFileSync(root+'/panel/static/index.html','utf8');
const dom=new JSDOM(html,{runScripts:'outside-only',url:'http://fixture.invalid'}),w=dom.window;
const catalog={models:[{id:'alpha',name:'Alpha',description:'Fixture',efforts:['high','ultra'],default_effort:'high'},{id:'beta',name:'Beta',description:'Fixture',efforts:['medium'],default_effort:'medium'}]};
let state={catalog,default:{coordinator:{model:'alpha',reasoning_effort:'high'},worker:{model:'beta',reasoning_effort:'medium'}},workflow:{activation:'manual',coordinator_mode:'current_thread',max_worker_turns:3},saved:{document:null,error:null,revision:'none'},scope:'project',project_root:'/fixture',global_revision:'none',source:'none'};
let saves=0; const clone=x=>JSON.parse(JSON.stringify(x));
w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false};
w.fusionTransport={initial:async()=>clone(state),request:async(path,body)=>{
 if(!body)return clone(state);assert.equal(path,'/api/selection');saves++;
 state.workflow=clone(body.workflow);state.saved={document:{selection:clone(body.selection),workflow:clone(body.workflow)},revision:String(saves),error:null};return {...clone(state.saved),state:clone(state)};
}};
w.eval(fs.readFileSync(root+'/panel/static/app.js','utf8'));
const tick=()=>new Promise(r=>setImmediate(r)),el=id=>w.document.getElementById(id),change=(id,value)=>{el(id).value=value;el(id).dispatchEvent(new w.Event('change'))};
(async()=>{await tick();assert.equal(el('planner-mode').value,'disabled');change('planner-mode','plan_only');assert(el('save').disabled);
change('planner-model','alpha');assert.equal(el('planner-effort').value,'high');change('planner-effort','ultra');change('max-planner-turns','3');assert(!el('save').disabled);el('save').click();await tick();assert.equal(saves,1);assert.equal(state.workflow.planner_mode,'plan_only');assert(el('save').disabled);
change('planner-model','beta');assert.equal(el('planner-effort').value,'medium');el('restore').click();el('discard-cancel').click();assert.equal(el('planner-model').value,'beta');el('restore').click();el('discard-confirm').click();await tick();assert.equal(el('planner-model').value,'alpha');assert.equal(el('planner-effort').value,'ultra');
change('planner-mode','disabled');el('save').click();await tick();assert.equal(state.workflow.planner_model,'alpha');assert.equal(saves,2);assert.equal(state.workflow.coordinator_mode,'current_thread');console.log(JSON.stringify({status:'passed',checks:['legacy disabled','enable requires choice','model effort adjustment','save roundtrip','cancel preserves edits','discard restores saved','disable retains choice','no planner dispatch'],saves}));w.close();})().catch(e=>{console.error(e);process.exit(1)});
