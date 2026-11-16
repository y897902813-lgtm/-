/* MuJoCo Lab V2.16.11.6 — project state, WebGL player and UDP derive from one content identity.
 * Motion edits use Studio project.replace; no second editable plan or hidden wire state.
 */
'use strict';
const $=id=>document.getElementById(id);
const API='/api/lab/projects/';
const STATE_FIELDS={is_moving:'运动标志',playback_state:'播放状态',motors:'电机位置',distance_pairs:'测距对'};
const TIMELINE_FIELDS={time_origin:'时钟起点',total_duration_s:'总时长',motors:'电机及运动段'};
const state={projectId:'',overview:null,config:null,run:null,lastFrame:null,lastState:null,inFlight:false,deploying:false,lastSubmittedAt:-Infinity,generating:false,runEnded:false,timelineEditMode:false,selectedSegment:null,udpView:'timeline',udpPackets:{timeline:null,state:null}};
let toaster=0;
function notify(message,kind='note'){const el=$('toast');el.textContent=message;el.style.color=kind==='error'?'#ef8d8c':'#f7c78a';clearTimeout(toaster);toaster=setTimeout(()=>el.textContent='',6500)}
function readableError(payload,status){let item=payload&&payload.detail?payload.detail:payload;if(typeof item==='string')return item;if(item&&typeof item==='object')return item.message||item.code||JSON.stringify(item);return`请求失败（HTTP ${status}）`}
async function api(path,{method='GET',body,signal}={}){
  const response=await fetch(path,{method,credentials:'same-origin',headers:{...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',signal});
  const payload=await response.json().catch(()=>null);
  if(!response.ok)throw new Error(readableError(payload,response.status));
  return payload;
}
function apiPath(suffix){return `${API}${encodeURIComponent(state.projectId)}/${suffix}`}
function displayIdentity(id){return id?`${id.slice(0,12)}…${id.slice(-5)}`:'—'}
function esc(text){return String(text??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}
function setSync(title,description,kind=''){const bar=$('statusStrip');bar.className=`status-strip ${kind}`;bar.title=description?`${title}：${description}`:title;$('syncTitle').textContent=title;$('syncMessage').textContent=description}
function updateButtons(){const ready=Boolean(state.overview?.ready),active=Boolean(state.run);$('deployButton').disabled=!ready||active||state.generating||state.deploying;$('stopButton').disabled=!active;$('generateButton').disabled=!state.projectId||state.generating}
function clearRun(reason){const existing=state.run;state.run=null;state.inFlight=false;state.runEnded=true;$('runText').textContent='—';$('runStatus').textContent='STANDBY';$('packetText').textContent=reason||'发送已停止';updateButtons();return existing}
// One fixed-height row per motor. Individual segments share a true time axis;
// numerical details live in the hover/focus tooltip, not in scroll-consuming rows.
function renderTimeline(timeline){
  const motors=Array.isArray(timeline?.motors)?timeline.motors:[];
  const all=motors.flatMap(motor=>Array.isArray(motor.segments)?motor.segments:[]);
  const origin=Number(state.overview?.simulation_start_s??0);
  const duration=Math.max(.000001, Number(timeline?.total_duration_s)||0,
    ...all.map(segment=>(Number(segment.start_time_s)||0)+(Number(segment.duration_s)||0)-origin));
  $('durationLabel').textContent=`总时长 ${duration.toFixed(3)} s`;
  $('segmentCount').textContent=`${all.length} 段`;
  $('timelineList').innerHTML=motors.length?motors.map((motor,motorIndex)=>{
    const blocks=(motor.segments||[]).map((segment,index)=>{
      const begin=Number(segment.start_time_s)||0,seconds=Math.max(0,Number(segment.duration_s)||0);
      const left=Math.min(100,Math.max(0,100*(begin-origin)/duration));
      const width=Math.max(0,Math.min(100-left,100*seconds/duration));
      const description=`${motor.name||motor.drive_id} / ${segment.name||segment.segment_id}\n`+
        `${begin.toFixed(3)}–${(begin+seconds).toFixed(3)} s\n`+
        `时长 ${seconds.toFixed(3)} s · 速度 ${segment.speed} ${motor.unit}/s\n`+
        `行程 ${segment.travel} ${motor.unit} · ${segment.profile||'s_curve'}`;
      return `<button type="button" class="gantt-block color-${index%4}" style="left:${left}%;width:${width}%" `+
        `data-drive-id="${esc(motor.drive_id)}" data-segment-id="${esc(segment.segment_id)}" `+
        `tabindex="${state.timelineEditMode?'0':'-1'}" title="${esc(description)}" aria-label="${esc(description)}"></button>`;
    }).join('');
    const name=esc(motor.name||motor.drive_id||`电机${motorIndex+1}`);
    return `<div class="motor-group"><div class="motor-heading" title="${name}">${name}</div><div class="motor-track">${blocks}</div></div>`;
  }).join(''):'<div class="placeholder">暂无电机时序</div>';
  $('timelinePane').classList.toggle('editing',Boolean(state.timelineEditMode));
  $('timelineEditButton').setAttribute('aria-pressed',String(Boolean(state.timelineEditMode)));
}
// UDP tabs are browser-only UI state. Each packet has its own independent cache;
// never replace the last confirmed timeline with a realtime frame (or vice versa).
const UDP_VIEWS={timeline:['udpTimelineTab','telemetryTimelineJson'],state:['udpStateTab','telemetryStateJson']};
function setUdpView(kind){
  if(!Object.hasOwn(UDP_VIEWS,kind))return;
  state.udpView=kind;
  for(const [name,[tabId,panelId]] of Object.entries(UDP_VIEWS)){
    const active=name===kind,tab=$(tabId),panel=$(panelId);
    tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;
    panel.hidden=!active;
  }
  $('runStatus').title=state.udpPackets[kind]?.label||
    (kind==='timeline'?'项目时序待加载':'等待服务端确认发出实时状态');
}
function showJsonPacket(packet,kind,label){
  if(!Object.hasOwn(UDP_VIEWS,kind))throw new Error('UDP 预览类型无效');
  const printed=JSON.stringify(packet,null,2);
  if(typeof printed!=='string')throw new Error('UDP 预览报文格式无效');
  state.udpPackets[kind]={packet,label};
  const panel=$(UDP_VIEWS[kind][1]);panel.textContent=printed;panel.title=label;
  if(state.udpView===kind)$('runStatus').title=label;
}
function resetUdpPackets(reason='未发送'){
  state.udpPackets={timeline:null,state:null};
  $('telemetryTimelineJson').textContent=reason+' · 等待项目时序';
  $('telemetryStateJson').textContent='等待已发送的实时 STATE 报文';
  for(const [,panelId] of Object.values(UDP_VIEWS))$(panelId).removeAttribute('title');
  setUdpView(state.udpView);
}
function plannedTimelinePreview(){
  if(!state.overview?.timeline||!state.config)return;
  try{
    showJsonPacket(previewPacket(state.overview.timeline,'timeline',state.config),'timeline',
      '未部署 · 当前项目时序与 UDP 字段配置预览（不是实际发送的 UDP 报文）');
  }catch(error){$('telemetryTimelineJson').textContent='时序预览不可用：'+error.message;}
}
function showOutgoingState(result){
  if(result.status!=='sent')return;  // throttled frames were NEVER sent
  try{
    const data={...result.state,run_id:state.run?.run_id,packet_seq:result.packet_seq};
    const packet=previewPacket(data,'state',state.config);
    packet.packet_seq=result.packet_seq;
    showJsonPacket(packet,'state',`STATE 已发送 · ${result.datagrams||1} 个数据报 · ${state.run?.run_id||''}`);
  }catch(_){
    showJsonPacket(result.state,'state','STATE 已发送 · 仅显示服务器状态源，JSON 字段投影不可用');
  }
}
function showTelemetry(data){if(!data)return;
  const motors=Array.isArray(data.motors)?data.motors:[],pairs=Array.isArray(data.distance_pairs)?data.distance_pairs:[];
  $('motorList').innerHTML=motors.length?motors.map(m=>{const valid=Number.isFinite(m.position),position=valid?`${Number(m.position).toFixed(3)} ${m.unit==='deg'?'°':'mm'}`:'—';const percent=Number.isFinite(m.percent)?Math.min(100,Math.max(0,m.percent)):0;
    return `<div class="motor-value-row"><div><small>${esc(m.name||m.drive_id)}</small><div class="motor-progress"><i style="width:${percent}%"></i></div></div><b>${esc(position)}</b></div>`}).join(''):'<div class="placeholder">当前模型没有采样电机。</div>';
  $('distanceList').innerHTML=pairs.length?pairs.map(p=>`<div class="distance-value-row"><div><small>${esc(p.name||p.pair_id)}</small></div><b>${p.valid&&Number.isFinite(p.distance_mm)?Number(p.distance_mm).toFixed(3)+' mm':'无效 · —'}</b></div>`).join(''):'<div class="placeholder">本模型未配置有效测距对。</div>';
  if(Number.isFinite(data.sim_time_s))$('sampleClock').textContent=`t = ${Number(data.sim_time_s).toFixed(3)} s`;
}
function previewFrame(frame){if(!frame||!Number.isFinite(frame.sim_time_s))return;
  if(!state.lastState)showTelemetry({motors:frame.motors,distance_pairs:[],sim_time_s:frame.sim_time_s});
  $('sampleClock').textContent=`t = ${frame.sim_time_s.toFixed(3)} s`;
}
function setPlayer(ready){const frame=$('animationFrame');
  frame.hidden=!ready;$('emptyPlayer').hidden=ready;
  if(ready){const uri=apiPath('viewer')+'?sequence_id='+encodeURIComponent(state.overview.identity.sequence_id);if(!frame.src.endsWith(uri))frame.src=uri;}
  else{frame.removeAttribute('src');state.lastFrame=null;state.lastState=null;}
  $('animationStatus').textContent=ready?'动画身份已校验':'需要重新生成';
}
async function loadOverview({reloadPlayer=false}={}){
  if(!state.projectId)return;
  const projectId=state.projectId;
  try{
    const overview=await api(apiPath('overview'));
    if(state.projectId!==projectId)return;
    const previous=state.overview?.identity?.sequence_id;
    const changed=previous&&previous!==overview.identity.sequence_id;
    state.overview=overview;state.config=overview.config;
    $('sequenceText').textContent=displayIdentity(overview.identity.sequence_id);$('sequenceText').title=overview.identity.sequence_id;
    renderTimeline(overview.timeline);
    $('editSequenceLink').href=`/models/${encodeURIComponent(state.projectId)}/editor/drives`;
    $('udpTargetLabel').textContent=`${state.config.remote_ip}:${state.config.remote_port}`;
    if(changed){clearRun('时序已变更');state.lastState=null;resetUdpPackets('时序已变更');setSync('已阻止发送','检测到模型或时序更改，旧动画与旧会话自动失效','error');}
    if(!state.udpPackets.timeline)plannedTimelinePreview();
    if(reloadPlayer||changed||$('animationFrame').hidden!==!overview.ready)setPlayer(overview.ready);
    if(!state.run){
      if(overview.ready)setSync('源数据已一致','本次导出动画与模型/时序指纹完全一致，可以部署','ready');
      else setSync('禁止发送',overview.reason||'请重新生成动画后再部署','error');
    }
    updateButtons();renderConfigDialog();
  }catch(e){if(state.projectId!==projectId)return;clearRun('无法连接服务器');setSync('模型不可用',e.message,'error');notify(e.message,'error');}
}
async function startGeneration(){if(!state.projectId||state.generating)return;
  clearRun('等待新动画');resetUdpPackets('正在生成动画');state.generating=true;updateButtons();setSync('生成中','正在用当前 MuJoCo 模型导出逐帧轨迹…');
  try{
    const job=await api(apiPath('generate'),{method:'POST'});
    while(true){
      await new Promise(resolve=>setTimeout(resolve,900));
      if(!state.projectId)break;
      const result=await api(`/api/jobs/${encodeURIComponent(job.job_id)}`);
      if(result.status==='completed'){state.generating=false;await loadOverview({reloadPlayer:true});notify('可信动画已生成，所有帧与当前时序绑定');break;}
      if(['failed','cancelled','timed_out'].includes(result.status))throw new Error(result.error?.message||result.message||'动画生成失败');
      const fraction=Math.round((Number(result.progress)||0)*100);
      setSync('生成中',`${result.message||'MuJoCo 轨迹采样'} · ${fraction}%`);
    }
  }catch(e){setSync('生成失败',e.message,'error');notify(e.message,'error');}
  finally{state.generating=false;updateButtons();}
}
async function startDeploy(){if(!state.overview?.ready||state.run||state.deploying)return;
  const deployedProject=state.projectId,deployedSequence=state.overview.identity.sequence_id,
    deployedConfig=state.config;
  state.deploying=true;updateButtons();
  try{const result=await api(apiPath('deploy'),{method:'POST'});
    if(state.projectId!==deployedProject||state.overview?.identity?.sequence_id!==deployedSequence||
       state.config!==deployedConfig||state.generating){
      // The UDP plan has already left the server: close its old session rather
      // than attaching the response to another project or a changed config.
      if(result.session_token){try{await api(`${API}${encodeURIComponent(deployedProject)}/stop`,
        {method:'POST',body:{session_token:result.session_token}})}catch(_){}}
      return;
    }
    state.run=result;state.lastSubmittedAt=-Infinity;state.runEnded=false;state.lastState=null;
    state.udpPackets.state=null;
    $('telemetryStateJson').textContent='已部署 · 等待当前会话发送首个 STATE 报文';
    $('telemetryStateJson').removeAttribute('title');
    // The successful deploy response now echoes the server-authoritative JSON
    // actually sent. In older-server compatibility mode mark reconstructed data
    // as a PREVIEW, never pretend it matches sampled initial motor positions.
    const actual=result.timeline_message;
    if(actual?.type==='timeline'&&actual.run_id===result.run_id&&
       actual.sequence_id===state.overview.identity.sequence_id&&actual.object_id===state.overview.identity.object_id){
      showJsonPacket(actual,'timeline',`TIMELINE 已发送 · ${result.timeline_datagrams} 个数据报 · ${result.run_id}`);
    }else{
      try{showJsonPacket(previewPacket(state.overview.timeline,'timeline',state.config),'timeline',
        '部署成功 · 服务器未返回实际 JSON，此处仅是项目时序预览')}catch(_){}
    }
    $('runText').textContent=displayIdentity(result.run_id);$('runText').title=result.run_id;
    $('runStatus').textContent='LIVE';$('packetText').textContent=`时序已发送 · ${result.timeline_datagrams} 个 UDP 包`;
    setSync('时序已部署',`目标 ${result.destination} · 等待播放器帧`, 'ready');
    notify('timeline 已发送，操作动画播放键后开始实时传输');
    if(state.lastFrame)void submitFrame(state.lastFrame);
  }catch(e){setSync('部署失败',e.message,'error');notify(e.message,'error')}
  finally{state.deploying=false;updateButtons()}
}
async function stopDeploy(){const running=clearRun('手动停止');if(!running)return;
  try{await api(apiPath('stop'),{method:'POST',body:{session_token:running.session_token}})}catch(e){notify(`停止时服务端提示：${e.message}`,'error')}
  setSync('已停止','当前 Lab 会话已经结束；重新部署将产生新的 run_id');
}
async function submitFrame(frame){if(!state.run||state.inFlight||!state.overview?.ready)return;
  if(!Number.isFinite(frame.sim_time_s))return;
  const now=performance.now(),interval=state.config.state_interval_ms||50;
  if(now-state.lastSubmittedAt<interval*.88&&frame.playback_state==='playing')return;
  state.inFlight=true;state.lastSubmittedAt=now;const session=state.run;
  try{
    const result=await api(apiPath('state'),{method:'POST',body:{session_token:session.session_token,sim_time_s:frame.sim_time_s,playback_state:frame.playback_state}});
    if(state.run!==session)return;
    state.lastState=result.state;showTelemetry(result.state);showOutgoingState(result);
    $('packetText').textContent=`${result.status==='sent'?'已发出':'已限流'} #${result.packet_seq}${result.datagrams?` · ${result.datagrams} 包`:''}`;
    setSync('实时同步中',`sequence ${displayIdentity(session.sequence_id)} · ${result.state.playback_state}`, 'ready');
    renderConfigDialog(false);
  }catch(e){if(state.run!==session)return;clearRun('发送被服务器阻断');
    setSync('一致性阻断',e.message,'error');notify(`UDP 发送已停止：${e.message}`,'error');}
  finally{state.inFlight=false;}
}
function sameIdentity(a,b){return a&&b&&a.object_id===b.object_id&&a.sequence_id===b.sequence_id&&a.model_fingerprint===b.model_fingerprint}
window.addEventListener('message',event=>{
  const iframe=$('animationFrame');if(event.origin!==location.origin||event.source!==iframe.contentWindow||iframe.hidden)return;
  const packet=event.data;if(!packet||packet.type!=='mujoco-lab-frame'||!['2.15.0','2.15.1','2.15.2','2.15.3','2.15.4','2.15.5','2.15.6','2.15.7','2.15.8','2.15.9','2.15.10','2.15.11','2.16.0','2.16.1','2.16.2','2.16.3','2.16.4','2.16.5','2.16.6','2.16.6.1','2.16.6.2','2.16.6.3','2.16.6.4','2.16.7','2.16.8','2.16.9','2.16.9.1','2.16.10','2.16.10.1','2.16.10.2','2.16.11','2.16.11.1','2.16.11.2','2.16.11.3','2.16.11.4','2.16.11.5','2.16.11.6'].includes(packet.lab_version))return;
  if(!sameIdentity(packet.identity,state.overview?.identity)){
    if(state.run)clearRun('播放器身份不匹配');setSync('不可信动画帧','当前播放器身份与时序 ID 不一致，UDP 发送已阻断','error');return;
  }
  if(!Number.isFinite(packet.sim_time_s)||!['playing','paused'].includes(packet.playback_state))return;
  state.lastFrame=packet;previewFrame(packet);
  if(state.run)void submitFrame(packet);
});
function checkboxFields(target,allowed,selected){target.replaceChildren();for(const [key,label] of Object.entries(allowed)){
  const lab=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.value=key;box.checked=selected.includes(key);box.addEventListener('change',()=>renderPreview());lab.append(box,document.createTextNode(label));target.append(lab);
}}
function chosenFields(id){return [...$(id).querySelectorAll('input:checked')].map(input=>input.value)}
function configFromDialog(){let state_extra,timeline_extra;
  try{state_extra=JSON.parse($('cfgStateExtra').value);timeline_extra=JSON.parse($('cfgTimelineExtra').value)}catch(e){throw new Error('自定义字段必须是合法 JSON：'+e.message)}
  if(!state_extra||Array.isArray(state_extra)||typeof state_extra!=='object'||!timeline_extra||Array.isArray(timeline_extra)||typeof timeline_extra!=='object')throw new Error('自定义字段只能是 JSON 对象');
  const output={remote_ip:$('cfgRemoteIp').value.trim(),remote_port:Number($('cfgRemotePort').value),local_ip:$('cfgLocalIp').value.trim(),packet_size:Number($('cfgPacketSize').value),packet_mode:$('cfgPacketMode').value,state_interval_ms:Number($('cfgInterval').value),state_fields:chosenFields('stateFieldChecks'),timeline_fields:chosenFields('timelineFieldChecks'),state_extra,timeline_extra};
  const reserved=['protocol_version','object_id','run_id','sequence_id','type','packet_seq','model_fingerprint',...Object.keys(STATE_FIELDS),...Object.keys(TIMELINE_FIELDS)];
  for(const key of [...Object.keys(state_extra),...Object.keys(timeline_extra)])if(reserved.includes(key))throw new Error(`自定义字段 ${key} 与系统字段冲突`);
  return output;
}
function renderConfigDialog(reloadInputs=true){if(!state.config)return;
  if($('udpDialog').open&&reloadInputs){const c=state.config;
    $('cfgRemoteIp').value=c.remote_ip;$('cfgRemotePort').value=c.remote_port;$('cfgLocalIp').value=c.local_ip;
    $('cfgPacketSize').value=c.packet_size;$('cfgPacketMode').value=c.packet_mode;$('cfgInterval').value=c.state_interval_ms;
    $('cfgStateExtra').value=JSON.stringify(c.state_extra||{},null,2);$('cfgTimelineExtra').value=JSON.stringify(c.timeline_extra||{},null,2);
    checkboxFields($('stateFieldChecks'),STATE_FIELDS,c.state_fields);
    checkboxFields($('timelineFieldChecks'),TIMELINE_FIELDS,c.timeline_fields);
  }
  if($('udpDialog').open)renderPreview();
}
function previewPacket(source,type,c){const chosen=c[type+'_fields'];let raw={...source,run_id:state.run?.run_id||'run_preview',type};
  const core={protocol_version:raw.protocol_version||'1.0',object_id:raw.object_id,run_id:raw.run_id,sequence_id:raw.sequence_id,type};
  if(type==='state'){core.packet_seq=state.run?.packet_seq||1;core.sim_time_s=raw.sim_time_s;}
  for(const field of chosen)if(raw[field]!==undefined)core[field]=raw[field];
  return {...core,...c[type+'_extra']};
}
function renderPreview(){if(!$('udpDialog').open||!state.overview)return;
  try{
    const c=configFromDialog();$('dialogError').textContent='';
    const id=state.overview.identity;
    const fallback={protocol_version:'1.0',object_id:id.object_id,sequence_id:id.sequence_id,type:'state',
      sim_time_s:state.lastFrame?.sim_time_s??0,playback_state:state.lastFrame?.playback_state||'paused',
      is_moving:false,motors:state.lastFrame?.motors?.map(m=>({...m,valid:Number.isFinite(m.position)}))||[],distance_pairs:[]};
    const real=state.lastState||fallback;
    $('stateJsonPreview').textContent=JSON.stringify(previewPacket(real,'state',c),null,2);
    const planned=state.overview.timeline;
    $('timelineJsonPreview').textContent=JSON.stringify(previewPacket(planned,'timeline',c),null,2);
  }catch(e){$('dialogError').textContent=e.message;$('stateJsonPreview').textContent='JSON 配置暂不可用';$('timelineJsonPreview').textContent='请检查自定义 JSON';}
}
async function saveConfig(event){event.preventDefault();if(!state.projectId)return;
  try{const config=configFromDialog();const result=await api(apiPath('udp-config'),{method:'PUT',body:config});
    state.config=result.config;$('udpTargetLabel').textContent=`${config.remote_ip}:${config.remote_port}`;
    $('udpDialog').close();if(state.run){clearRun('UDP 配置已更改');setSync('配置更改','配置已保存，需重新部署才能继续发送');}
    state.lastState=null;resetUdpPackets('UDP 配置已更新');plannedTimelinePreview();notify('UDP 与 JSON 配置已保存到本模型');
  }catch(e){$('dialogError').textContent=e.message;notify(e.message,'error')}
}
async function copyPreview(id){const text=$(id).textContent;try{await navigator.clipboard.writeText(text);notify('JSON 已复制到剪贴板')}catch(e){notify('复制失败：请手动选中预览内容','error')}}
const SPLIT_STORAGE_KEY='mujocoLab.timelineRatio.v2151';
const DEFAULT_TIMELINE_RATIO=.4;
function initRightPanelSplitter(){
  const root=$('rightStack'),handle=$('rightPanelResizer');let ratio=DEFAULT_TIMELINE_RATIO,drag=null;
  try{const stored=Number(localStorage.getItem(SPLIT_STORAGE_KEY));if(Number.isFinite(stored)&&stored>.05&&stored<.95)ratio=stored}catch(_){}
  function apply(value,persist=false){
    const available=root.clientHeight-(handle.offsetHeight||8);
    if(available<1)return;
    const minTop=Math.min(235,Math.max(108,available*.32));
    const minBottom=Math.min(150,Math.max(88,available*.24));
    const px=Math.max(minTop,Math.min(available-minBottom,value*available));
    ratio=px/available;
    root.style.setProperty('--timeline-size',`${px.toFixed(2)}px`);
    const percent=Math.round(ratio*100);
    handle.setAttribute('aria-valuenow',String(percent));
    handle.setAttribute('aria-valuetext',`时序区域占 ${percent}%`);
    if(persist){try{localStorage.setItem(SPLIT_STORAGE_KEY,String(ratio))}catch(_){}}
  }
  handle.addEventListener('pointerdown',event=>{
    if(event.button!==0)return;
    event.preventDefault();drag={id:event.pointerId,startY:event.clientY,startRatio:ratio,area:Math.max(1,root.clientHeight-(handle.offsetHeight||8))};
    handle.classList.add('dragging');handle.setPointerCapture(event.pointerId);
  });
  handle.addEventListener('pointermove',event=>{
    if(!drag||drag.id!==event.pointerId)return;
    apply(drag.startRatio+(event.clientY-drag.startY)/drag.area);
  });
  const finish=(event,cancelled)=>{
    if(!drag||drag.id!==event.pointerId)return;
    if(cancelled)apply(drag.startRatio);else apply(ratio,true);
    drag=null;handle.classList.remove('dragging');
    try{if(handle.hasPointerCapture(event.pointerId))handle.releasePointerCapture(event.pointerId)}catch(_){}
  };
  handle.addEventListener('pointerup',event=>finish(event,false));
  handle.addEventListener('pointercancel',event=>finish(event,true));
  handle.addEventListener('lostpointercapture',event=>finish(event,true));
  handle.addEventListener('dblclick',()=>apply(DEFAULT_TIMELINE_RATIO,true));
  handle.addEventListener('keydown',event=>{
    if(!['ArrowUp','ArrowDown','Home','End'].includes(event.key))return;
    event.preventDefault();
    if(event.key==='Home')apply(0,true);
    else if(event.key==='End')apply(1,true);
    else apply(ratio+(event.key==='ArrowDown'?.025:-.025),true);
  });
  if(typeof ResizeObserver==='function')new ResizeObserver(()=>{if(!drag)apply(ratio)}).observe(root);
  window.addEventListener('resize',()=>{if(!drag)apply(ratio)});
  apply(ratio);
}
function openSegmentEdit(driveId,segmentId){
  const motor=(state.overview?.timeline?.motors||[]).find(item=>item.drive_id===driveId);
  const seg=motor?.segments?.find(item=>item.segment_id===segmentId);
  if(!seg)return;
  if(state.overview?.project?.lifecycle!=='checked_out'){
    notify('需要先在 Studio 中正式签出该模型，才能修改运动时序','error');return;
  }
  if(!['s_curve','smoothstep'].includes(seg.profile)||seg.points?.length||seg.mapping_source_joint_id){
    notify('映射、外部 CSV 与自定义点运动段请使用 Studio Editor 编辑','error');return;
  }
  state.selectedSegment={driveId,segmentId,mode:seg.mode};
  $('segmentEditTitle').textContent=`${motor.name||driveId} / ${seg.name||segmentId}`;
  $('segmentEditDetail').textContent='更改后将写入当前项目；旧动画和 UDP 会话会自动失效';
  $('segmentEditStart').value=Number(seg.start_time_s);
  $('segmentEditDuration').value=Number(seg.duration_s);
  $('segmentEditSpeed').value=Number(seg.speed);
  $('segmentEditTravel').value=Number(seg.travel);
  $('segmentEditDuration').disabled=seg.mode!=='duration';
  $('segmentEditSpeed').disabled=seg.mode!=='speed';
  $('segmentEditMode').textContent=seg.mode==='duration'?'当前按时长驱动；速度由运动行程和时长推导。':'当前按速度驱动；时长由运动行程和速度推导。';
  $('segmentEditError').textContent='';$('segmentEditDialog').showModal();
}
async function saveSegmentEdit(event){
  event.preventDefault();const active=state.selectedSegment;if(!active)return;
  const start=Number($('segmentEditStart').value),duration=Number($('segmentEditDuration').value),speed=Number($('segmentEditSpeed').value),travel=Number($('segmentEditTravel').value);
  if(![start,duration,speed,travel].every(Number.isFinite)){ $('segmentEditError').textContent='必须输入有限数字';return; }
  if(start<0||duration<=0){$('segmentEditError').textContent='起始时间不能为负，时长必须大于 0';return;}
  $('segmentEditSave').disabled=true;
  try{
    const changed=await api(apiPath(`segments/${encodeURIComponent(active.driveId)}/${encodeURIComponent(active.segmentId)}`),{
      method:'PUT',body:{expected_sequence_id:state.overview.identity.sequence_id,
        expected_updated_at:state.overview.project.updated_at,
        start_time_s:start,duration_s:duration,speed,travel}
    });
    $('segmentEditDialog').close();clearRun('时序已修改');state.lastState=null;
    await loadOverview({reloadPlayer:true});
    setSync('时序已保存','已更新项目及模型时序库；旧动画必须重新生成','error');
    notify(`运动段已保存 · ${changed.tsjson_name||'TSJSON 已同步'}；CSV 已归入交付数据/表格文件夹`);
  }catch(error){$('segmentEditError').textContent=error.message;notify(error.message,'error');}
  finally{$('segmentEditSave').disabled=false;}
}
function attachEvents(){
  initRightPanelSplitter();setUdpView('timeline');
  for(const [kind,[tabId]] of Object.entries(UDP_VIEWS)){
    $(tabId).addEventListener('click',()=>setUdpView(kind));
    $(tabId).addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
      event.preventDefault();
      const target=event.key==='Home'?'timeline':event.key==='End'?'state':kind==='timeline'?'state':'timeline';
      setUdpView(target);$(UDP_VIEWS[target][0]).focus();
    });
  }
  $('timelineEditButton').addEventListener('click',()=>{state.timelineEditMode=!state.timelineEditMode;renderTimeline(state.overview?.timeline);});
  $('timelineList').addEventListener('click',event=>{const block=event.target.closest('.gantt-block');if(block&&state.timelineEditMode)openSegmentEdit(block.dataset.driveId,block.dataset.segmentId)});
  $('segmentEditClose').addEventListener('click',()=>$('segmentEditDialog').close());
  $('segmentEditCancel').addEventListener('click',()=>$('segmentEditDialog').close());
  $('segmentEditForm').addEventListener('submit',saveSegmentEdit);
  $('projectSelect').addEventListener('change',async event=>{clearRun('已切换项目');resetUdpPackets('切换项目');state.projectId=event.target.value;state.overview=null;state.config=null;state.lastState=null;state.lastFrame=null;history.replaceState(null,'',state.projectId?`/lab?project_id=${encodeURIComponent(state.projectId)}`:'/lab');await loadOverview({reloadPlayer:true});});
  $('generateButton').addEventListener('click',startGeneration);$('deployButton').addEventListener('click',startDeploy);$('stopButton').addEventListener('click',stopDeploy);
  $('udpSettingsButton').addEventListener('click',()=>{$('udpDialog').showModal();$('dialogError').textContent='';renderConfigDialog(true)});
  $('udpClose').addEventListener('click',()=>$('udpDialog').close());$('udpCancel').addEventListener('click',()=>$('udpDialog').close());
  $('udpForm').addEventListener('submit',saveConfig);$('copyState').addEventListener('click',()=>copyPreview('stateJsonPreview'));$('copyTimeline').addEventListener('click',()=>copyPreview('timelineJsonPreview'));
  for(const name of ['cfgRemoteIp','cfgRemotePort','cfgLocalIp','cfgPacketSize','cfgPacketMode','cfgInterval','cfgStateExtra','cfgTimelineExtra'])$(name).addEventListener('input',renderPreview);
}
async function init(){attachEvents();
  try{
    const projects=await api('/api/projects');if(!Array.isArray(projects))throw new Error('项目列表无效');
    const selector=$('projectSelect');selector.replaceChildren();
    if(!projects.length){const opt=document.createElement('option');opt.value='';opt.textContent='没有可用项目';selector.append(opt);setSync('没有项目','请先在 MuJoCoHub 创建或选择模型');return;}
    for(const item of projects){const opt=document.createElement('option');opt.value=item.id;opt.textContent=item.name||item.id;selector.append(opt)}
    const param=new URLSearchParams(location.search).get('project_id');state.projectId=projects.some(p=>p.id===param)?param:projects[0].id;
    selector.value=state.projectId;await loadOverview({reloadPlayer:true});
    // Periodic verification catches edits in a separate Editor tab and revokes stale viewers.
    setInterval(async()=>{if(state.generating||!state.projectId)return;
      const projectId=state.projectId,previous=state.overview?.identity?.sequence_id;
      try{const fresh=await api(`${API}${encodeURIComponent(projectId)}/overview`);
      if(projectId!==state.projectId)return;
      if(state.overview&&fresh.identity.sequence_id!==previous){state.overview=fresh;clearRun('时序已修改');setPlayer(false);await loadOverview({reloadPlayer:true});setSync('版本不匹配','模型或时序已更新，必须重新生成动画','error')}
    }catch(_){}},3500);
  }catch(e){setSync('无法加载 Lab',e.message,'error');notify(`登录或网络错误：${e.message}；请先从 MuJoCoHub 登录`, 'error');}
}
void init();
