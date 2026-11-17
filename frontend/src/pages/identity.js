import {identity,datasets as datasetsApi} from '../api/entities.js';
import {api} from '../api/client.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {esc,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {RebuildState} from '../constants/enums.js';
const bindingRow=(b,canWrite)=>'<li><span class="binding-id">'+esc(b.work_id)+' @ '+esc(b.warehouse)+'</span><span>'+b.valid_from+' ~ '+(b.valid_to||'至今')+'</span>'+(b.state==='active'?'<button class="text-button" data-revoke="'+b.id+'" '+(canWrite?'':'disabled')+'>停用</button>':'<em>已停用</em>')+'</li>';
const personCard=(p,persons,canWrite,isAdmin)=>{
 const others=persons.filter(x=>x.status==='active'&&x.id!==p.id);
 return '<article class="person-card"><div class="person-head"><strong>'+esc(p.name)+'</strong>'+(p.status==='merged'?'<span class="status merged">已归并 → '+esc(p.merged_into_name||'')+'</span>':'<span class="status active">在册</span>')+'</div>'
 +(p.note?'<p class="hint">'+esc(p.note)+'</p>':'')
 +(p.bindings.length?'<ul class="binding-list">'+p.bindings.map(b=>bindingRow(b,canWrite)).join('')+'</ul>':'<p class="hint">尚无归属记录</p>')
 +(isAdmin?(p.status==='active'
   ?(others.length?'<form class="merge-form" data-person="'+p.id+'"><div class="merge-row"><select name="into_id">'+others.map(x=>'<option value="'+x.id+'">归并到 '+esc(x.name)+'</option>').join('')+'</select><button type="submit" class="button small">归并</button></div></form>':'')
   :'<button class="button small" data-split="'+p.id+'">拆分此归并</button>'):'')
 +'</article>';
};
const conflictCard=c=>'<div class="conflict"><div class="section-title"><h3>'+esc(c.label)+'</h3><span>'+c.records.length+' 条测时归属同一人</span></div>'
 +'<div class="table-wrap"><table><thead><tr><th>行号</th><th>原始工号</th><th>仓别</th><th>测时日期</th><th>原路线/秒</th><th>新路线/秒</th></tr></thead><tbody>'
 +c.records.map(r=>'<tr><td>'+(r.index+1)+'</td><td>'+esc(r.operator)+'</td><td>'+esc(r.warehouse||'—')+'</td><td>'+esc(r.date||'—')+'</td><td>'+esc(r.before)+'</td><td>'+esc(r.after)+'</td></tr>').join('')
 +'</tbody></table></div><div class="resolve-row">'
 +[['first','保留最早行'],['last','保留最新行'],['none','全部排除']].map(([v,l])=>'<label><input type="radio" name="res-'+esc(c.key)+'" value="'+v+'"> '+l+'</label>').join('')
 +'</div></div>';
const previewBlock=(r,isAdmin)=>{
 const p=r.preview;
 const counts=[['测时记录',p.total],['已归属',p.resolved],['未归属 · 按原工号',p.unresolved],['无测时日期',p.legacy],['受影响人员',p.affected_total],['配对冲突',p.conflicts.length]];
 return '<div class="preview-block"><div class="section-title"><h2>身份重建预览 · #'+r.id+'</h2><span>确认后整批重建并一次性切换</span></div>'
 +'<div class="metrics">'+counts.map(([k,v])=>'<div><span>'+k+'</span><strong>'+v+'</strong></div>').join('')+'</div>'
 +(p.affected.length?'<h3>受影响人员</h3><ul class="affected-list">'+p.affected.map(a=>'<li><strong>'+esc(a.label)+'</strong><span>原身份 '+a.from.map(esc).join('、')+' · '+a.records+' 条测时</span></li>').join('')+'</ul>':'<p class="hint">没有人员的归属会发生变化。</p>')
 +(p.conflicts.length?'<h3>配对冲突 · 需逐起选择处理方式</h3>'+p.conflicts.map(conflictCard).join(''):'<p class="hint">无配对冲突。</p>')
 +(isAdmin?'<button class="primary" id="confirm-rebuild">确认并整批切换身份依据</button>':'<p class="hint">需业务负责人确认后才会切换；冲突未解不放行。</p>')
 +'</div>';
};
const rebuildRow=r=>'<article class="rebuild-row"><div><strong>#'+r.id+' · '+esc(RebuildState[r.state]||r.state)+'</strong><p>配对冲突 '+((r.preview&&r.preview.conflicts)||[]).length+' 起 · 进度 '+r.progress+'/'+r.total+(r.map_version?' · 身份依据 v'+r.map_version:'')+'</p><small>'+date(r.created_at)+(r.finished_at?' · 完成于 '+date(r.finished_at):'')+(r.error?' · '+esc(r.error):'')+'</small></div></article>';
export async function identityPage(){
 const [persons,sets,audits,rebuilds]=await Promise.all([identity.persons(),datasetsApi.list(),api('/audits'),identity.rebuilds()]);
 const canWrite=session.user.role!=='viewer',isAdmin=session.user.role==='admin';
 workspace.identity=workspace.identity||{};
 const sel=Number(workspace.identity.datasetId)||(sets[0]&&sets[0].id);
 const dataset=sets.find(d=>d.id===sel);
 const preview=workspace.identity.preview&&workspace.identity.preview.dataset_id===sel?workspace.identity.preview:null;
 const myRebuilds=rebuilds.filter(r=>r.dataset_id===sel);
 workspace.identity.switching=myRebuilds.some(r=>['confirmed','rebuilding'].includes(r.state));
 const idAudits=audits.filter(a=>/^(person|binding|identity)\./.test(a.action));
 return heading('03 / IDENTITY','人员身份簿','仓别 + 工号 + 生效期 → 稳定人员。换号归并、误归并拆分；已有批次先预览受影响人员与配对冲突，确认后整批重建身份依据并一次性切换。')
 +'<div class="identity-grid"><section class="panel"><div class="section-title"><h2>稳定人员</h2><span>'+persons.filter(p=>p.status==='active').length+' 人在册</span></div>'
 +'<div class="person-list">'+(persons.map(p=>personCard(p,persons,canWrite,isAdmin)).join('')||'<p class="empty">尚无稳定人员，请先登记。</p>')+'</div>'
 +'<div class="section-title"><h2>登记与归属</h2></div>'
 +'<form id="person-form" class="inline-form"><input name="name" required minlength="2" maxlength="80" placeholder="稳定人员姓名"><input name="note" maxlength="300" placeholder="备注（班组、入离职等）"><button type="submit" class="button small" '+(canWrite?'':'disabled')+'>新增人员</button></form>'
 +'<form id="binding-form"><div class="parameter-grid"><label>稳定人员<select name="person_id">'+persons.filter(p=>p.status==='active').map(p=>'<option value="'+p.id+'">'+esc(p.name)+'</option>').join('')+'</select></label><label>仓别<input name="warehouse" required maxlength="60" placeholder="东仓"></label><label>工号<input name="work_id" required maxlength="60" placeholder="T-107"></label><label>生效开始<input type="date" name="valid_from" required></label><label>生效结束（留空为至今）<input type="date" name="valid_to"></label></div><button type="submit" class="button small" '+(canWrite?'':'disabled')+'>登记归属</button><p class="hint">同一仓别工号在重叠生效期内归属他人时，登记会被阻止并留痕。</p></form>'
 +'</section><section><div class="panel switch-panel"><div class="section-title"><h2>批次身份切换</h2><span>'+(dataset&&dataset.identity_version?'当前身份依据 v'+dataset.identity_version:'未启用身份依据 · 按原始工号分析')+'</span></div>'
 +(sets.length?'<label>数据批次<select id="identity-dataset">'+sets.map(d=>'<option value="'+d.id+'" '+(d.id===sel?'selected':'')+'>'+esc(d.name)+'</option>').join('')+'</select></label><button class="button" id="preview-rebuild" '+(canWrite?'':'disabled')+'>预览受影响人员与配对冲突</button>':'<p class="empty">尚无数据批次。</p>')
 +(preview?previewBlock(preview,isAdmin):'')
 +(myRebuilds.length?'<div class="section-title"><h3>切换进度</h3><span>'+myRebuilds.length+' 次重建</span></div>'+myRebuilds.map(rebuildRow).join(''):'')
 +'</div><div class="panel"><div class="section-title"><h2>沿革与冲突</h2><span>最近 '+idAudits.length+' 条</span></div>'
 +(idAudits.length?'<ul class="timeline">'+idAudits.slice(0,12).map(a=>'<li><strong>'+esc(a.action)+'</strong><span>'+esc(a.actor)+' · '+date(a.at)+'</span></li>').join('')+'</ul>':'<p class="hint">尚无身份相关记录。</p>')
 +'</div></section></div>';
}
export function bindIdentity(refresh){
 document.querySelector('#identity-dataset')?.addEventListener('change',e=>{workspace.identity.datasetId=Number(e.target.value);workspace.identity.preview=null;refresh();});
 document.querySelector('#preview-rebuild')?.addEventListener('click',async()=>{
  try{const r=await identity.preview(Number(document.querySelector('#identity-dataset').value));workspace.identity.preview=r;notify('预览已生成：受影响 '+r.preview.affected_total+' 人 · 配对冲突 '+r.preview.conflicts.length+' 起');await refresh();}catch(e){notify(e.message,true);}
 });
 document.querySelector('#confirm-rebuild')?.addEventListener('click',async()=>{
  const r=workspace.identity.preview,resolutions={};
  for(const c of r.preview.conflicts){
   const picked=document.querySelector('input[name="res-'+c.key+'"]:checked');
   if(!picked){notify('配对冲突「'+c.label+'」尚未选择处理方式，冲突未解不放行',true);return;}
   resolutions[c.key]=picked.value;
  }
  try{await identity.confirm(r.id,{resolutions});workspace.identity.preview=null;notify('已确认，后台整批重建身份依据并一次性切换');await refresh();}catch(e){notify(e.message,true);}
 });
 submit(document.querySelector('#person-form'),async f=>{await identity.createPerson({name:f.get('name'),note:f.get('note')||''});notify('人员已登记');await refresh();});
 submit(document.querySelector('#binding-form'),async f=>{await identity.createBinding({person_id:Number(f.get('person_id')),warehouse:f.get('warehouse'),work_id:f.get('work_id'),valid_from:f.get('valid_from'),valid_to:f.get('valid_to')||null});notify('归属已登记');await refresh();});
 document.querySelectorAll('.merge-form').forEach(form=>submit(form,async f=>{await identity.merge(Number(form.dataset.person),Number(f.get('into_id')));notify('已归并；相关批次需重新预览并确认后切换');await refresh();}));
 document.querySelectorAll('[data-split]').forEach(b=>b.onclick=async()=>{try{await identity.split(Number(b.dataset.split));notify('已拆分，按原始测时重新归属');await refresh();}catch(e){notify(e.message,true);}});
 document.querySelectorAll('[data-revoke]').forEach(b=>b.onclick=async()=>{try{await identity.revoke(Number(b.dataset.revoke));notify('归属已停用');await refresh();}catch(e){notify(e.message,true);}});
 if(workspace.identity?.switching){clearTimeout(workspace.identity.timer);workspace.identity.timer=setTimeout(refresh,1500);}
}
