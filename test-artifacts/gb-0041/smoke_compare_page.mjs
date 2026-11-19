// 对比检验页面渲染冒烟测试：node smoke_compare_page.mjs
// 打桩浏览器全局与 /api 响应，验证三种任务状态下页面的报告口径。
globalThis.location={port:'18245',hash:'#compare'};
globalThis.localStorage={getItem:()=>null,setItem:()=>{},removeItem:()=>{}};
const F1='轴承磨损',F2='转子偏心';
const runs=[
  {id:1,name:'研究甲',state:'completed',source_id:1,created_at:'2026-11-01T01:00:00+00:00',parameters:{folds:3}},
  {id:2,name:'研究乙',state:'completed',source_id:1,created_at:'2026-11-01T02:00:00+00:00',parameters:{folds:5}},
  {id:3,name:'别批研究',state:'completed',source_id:2,created_at:'2026-11-01T03:00:00+00:00',parameters:{folds:3}}];
const comparisons=[
  {id:11,source_id:1,name:'排队中检验',run_a_id:1,run_b_id:2,fault_a:F1,fault_b:F2,attribution_version:1,state:'queued',done:0,total_swaps:0,created_at:'2026-11-02T01:00:00+00:00'},
  {id:12,source_id:1,name:'完成检验',run_a_id:1,run_b_id:2,fault_a:F1,fault_b:F2,attribution_version:1,state:'completed',done:200000,total_swaps:200000,created_at:'2026-11-02T02:00:00+00:00',
   result:{probability:0.3145,hits:62900,total_swaps:200000,observed:2,mode:'sampled',pairs:240,bearings:120,misses:{a:{[F1]:3,[F2]:1},b:{[F1]:1,[F2]:3}},faults:[F1,F2],seed:99,attribution_version:1,explanation:'说明文字'}},
  {id:13,source_id:1,name:'失败检验',run_a_id:1,run_b_id:2,fault_a:F1,fault_b:F2,attribution_version:2,state:'failed',done:1024,total_swaps:4096,error:'缺轴承归属：样本 R007 在归属版本 v2 中没有轴承归属，停止计算',created_at:'2026-11-02T03:00:00+00:00'}];
const attributions=[{id:2,source_id:1,version:2,note:'归属更正',bearings:100,samples:240,created_at:'2026-11-02T00:00:00+00:00'},{id:1,source_id:1,version:1,note:'初始归属',bearings:120,samples:240,created_at:'2026-11-01T00:00:00+00:00'}];
globalThis.fetch=async(url,opts={})=>{
  const path=url.replace('/api','');
  const json=()=>({ok:true,status:200,json:async()=>responses[path]});
  return json()};
const responses={'/sources/1/attributions':attributions,'/runs/1':{...runs[0],result:{labels:['正常',F1,F2]}},'/runs/2':{...runs[1],result:{labels:['正常',F1,F2]}}};
const {comparePage}=await import('/workspace/frontend/src/pages/compare.js');
const {research}=await import('/workspace/frontend/src/stores/research.js');
const {session}=await import('/workspace/frontend/src/stores/session.js');
session.user={email:'admin@t.demo',role:'admin'};
research.sources=[{id:1,name:'批次一',record_count:240},{id:2,name:'批次二',record_count:240}];
research.runs=runs;research.comparisons=comparisons;research.notes=[];research.sourceId=1;
const html=await comparePage();
const assert=(cond,msg)=>{if(!cond){console.error('FAIL:',msg);process.exit(1)}};
assert(html.includes('两项研究的漏判差'),'页面标题');
assert(html.includes('研究甲'),'研究选项');
assert(html.includes('v2 · 100轴承'),'归属版本选项含新版');
// 完成的任务才报告概率与换位总数
const done=html.split('完成检验')[1];
assert(done.includes('0.3145')&&done.includes('>200000<'),'完成检验报告概率与换位总数');
assert(done.includes('实测最大漏判差'),'完成检验报告实测差');
assert(done.includes('归属已另出 v2'),'已有新版归属时提示仍按原版');
// 进行中的任务不报告概率与换位总数（不出现指标块）
const queued=html.split('排队中检验')[1].split('完成检验')[0];
assert(queued.includes('正在换位评估')&&!queued.includes('class="metrics"')&&!queued.includes('实测最大漏判差'),'排队中不报告概率与换位总数');
// 失败的任务报告停算原因并可重试
const failed=html.split('失败检验')[1];
assert(failed.includes('缺轴承归属')&&failed.includes('data-retry="13"'),'失败检验显示停算原因与重试');
console.log('compare page smoke ok');
