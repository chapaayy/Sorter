'use strict';
const app=document.getElementById('app');
const state={tab:'home',me:null,runs:[],active:null,batch:localStorage.getItem('ps.batch')||'',references:{total:0,sam:[]},batchInfo:{photos:0},model:null,uploading:false,uploadPercent:0,uploadLabel:'',runTimer:null,fullTimer:null,pollingRun:false,error:'',resultMode:'sam',results:null,logs:[],threshold:0.50};
const H=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=s=>{if(!s)return '—';return new Date(s).toLocaleString('ru-RU')};
async function api(url,opts={}){const response=await fetch('/api'+url,{credentials:'same-origin',...opts});if(!response.ok){let detail='HTTP '+response.status;try{const data=await response.json();detail=typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||data)}catch{}throw Error(detail)}return response.headers.get('content-type')?.includes('application/json')?response.json():response;}
function jopts(body,method='POST'){return {method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}}
function report(error){state.error=String(error?.message||error);render()}
function banner(){return state.error?`<div class="error">${H(state.error)} <button class="button" onclick="state.error='';render()">Закрыть</button></div>`:''}
async function boot(){try{
  state.me=await api('/auth/me');
  await refresh();
  clearInterval(state.runTimer);clearInterval(state.fullTimer);
  state.runTimer=setInterval(pollRunProgress,1250);
  state.fullTimer=setInterval(refresh,12000);
  render();
}catch{renderLogin()}}
function renderLogin(){app.innerHTML=`<div class="login-bg"><form class="login" id="login"><span class="eyebrow">OUTDOOR · PHOTOSORTER</span><h1>Вход в панель</h1><p class="sub">Приватный сервер сортировки фотографий</p><label>Логин</label><input name="username" autocomplete="username" value="admin" required><label>Пароль</label><input name="password" type="password" autocomplete="current-password" required>${banner()}<button class="button primary">Войти</button></form></div>`;document.getElementById('login').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target);try{state.error='';await api('/auth/login',jopts({username:f.get('username'),password:f.get('password')}));await boot()}catch(error){report(error)}}}
async function refresh(){if(!state.me)return;try{const [runs,refs,model]=await Promise.all([api('/runs'),api('/references'),api('/models')]);state.runs=runs.runs||[];state.active=state.runs.find(r=>r.id===state.active?.id)||state.runs[0]||null;state.references=refs;state.model=model;if(state.batch){try{state.batchInfo=await api('/batches/'+state.batch)}catch{state.batch='';localStorage.removeItem('ps.batch')}}if(state.tab==='logs'&&state.active){state.logs=(await api('/logs/'+encodeURIComponent(state.active.id))).events||[]}if(state.tab==='results'&&state.active?.models?.megaloc?.status==='completed'){state.results=await api('/results/'+encodeURIComponent(state.active.id)+'/megaloc')}render()}catch(error){console.error(error)}}
function render(){if(!state.me)return renderLogin();let body=state.tab==='home'?home():state.tab==='results'?results():logs();app.innerHTML=`<div class="layout"><aside class="sidebar"><div class="brand"><div class="brand-icon">▦</div><div><b>OUTDOOR</b><small>PHOTOSORTER 4.1</small></div></div><div class="nav-label">ПРИЛОЖЕНИЕ</div>${[['home','Главная','⌂'],['results','Результаты','▦'],['logs','Логи','›_']].map(t=>`<button class="nav ${state.tab===t[0]?'active':''}" onclick="state.tab='${t[0]}';refresh()"><span class="ico">${t[2]}</span><span>${t[1]}</span></button>`).join('')}<div class="spacer"></div><div class="status">● VPS · HTTPS · MegaLoc CPU</div></aside><div class="main"><header class="top"><div>Outdoor　›　<b>${H({home:'Главная',results:'Результаты',logs:'Логи'}[state.tab])}</b></div><div>Серверный режим　 <button class="button" onclick="signout()">Выход</button></div></header><main class="content">${body}</main></div></div>`}

const RUN_STEPS={
  validate_queries:1,loading:2,queries:3,
  grouping:4,grouping_merge:4,grouping_diagnostics:4,
  references:5,matching:6,saving:7,export:7
};
const RUN_STATUS_LABELS={
  queued:'В очереди',running:'Обработка выполняется',stopping:'Остановка обработки',
  completed:'Обработка завершена',completed_with_errors:'Завершено с ошибками',
  stopped:'Обработка остановлена',failed:'Ошибка обработки',interrupted:'Обработка прервана'
};
function runDuration(seconds){
  if(!Number.isFinite(Number(seconds))||Number(seconds)<0)return '—';
  const s=Math.max(0,Math.round(Number(seconds)));
  const h=Math.floor(s/3600),m=Math.floor(s%3600/60),r=s%60;
  return (h?h+' ч ':'')+(m||h?m+' мин ':'')+r+' с';
}
function runProgressCard(run){
  const p=run?.progress||{},status=run?.status||'idle';
  const active=['queued','running','stopping'].includes(status);
  const working=status==='running'||status==='stopping';
  const stage=p.stage||'';
  const step=RUN_STEPS[stage];
  const current=Number(p.current),total=Number(p.total);
  const counted=working&&Number.isFinite(current)&&Number.isFinite(total)&&total>0&&
    ['validate_queries','queries','grouping','grouping_diagnostics','references','matching','saving'].includes(stage);
  const count=Math.max(0,Math.min(total,current));
  const percent=counted?Math.min(100,Math.max(0,100*count/total)):null;
  const unit=stage==='references'?'Образцов':'ФО';
  const title=run?RUN_STATUS_LABELS[status]||status:'Готово к обработке';
  const stepLabel=step?'Этап '+step+' из 7':'';
  const stageLabel=working?(p.stage_label||'Подготовка обработки'):
    status==='queued'?'Задание ожидает запуска':
    status==='completed'?'Все этапы завершены':
    status==='failed'?run.error||'Ошибка выполнения':
    status==='stopped'?'Остановлено пользователем':
    status==='interrupted'?'Выполнение было прервано':
    !run?'ФО → Группы ФО → Образцы → Готовые фотки':'';
  const name=String(p.detail||'').split(/[\\/]/).pop().replace(/^[a-f0-9]{20}_/i,'');
  const fileDetail=working&&/\.(jpg|jpeg|png|webp|bmp|tif|tiff)$/i.test(name);
  const eta=Number(p.estimated_remaining_seconds);
  const approx=working&&['references','matching','saving','export'].includes(stage)&&
    p.eta_status==='measured'&&p.estimated_remaining_seconds!=null&&
    Number(p.elapsed_seconds)>=30&&Number.isFinite(eta)&&eta>0;
  return `<div class="line">
    <div><h2>${H(title)}</h2><p>${H(stageLabel)}</p></div>
    <div class="btnrow">${stepLabel?`<span class="pill">${H(stepLabel)}</span>`:''}
    ${active?`<button class="button danger" onclick="stopRun()">Остановить</button>`:
      `<button class="button primary" ${!state.model?.models?.[0]?.available||!state.batchInfo.photos||!state.references.total||state.uploading?'disabled':''} onclick="startRun()">▶ Начать обработку</button>`}</div>
  </div>
  ${counted?`<div class="run-stage-head"><strong>Прогресс этапа</strong><span>${count} из ${total} ${unit} · ${percent.toFixed(1)}%</span></div>
    <div class="bar" aria-label="Прогресс текущего этапа"><span style="width:${percent}%"></span></div>`:
    working?`<div class="run-status-hint">Этап выполняется · подробный счётчик пока недоступен</div>`:''}
  ${fileDetail?`<div class="run-status-hint" title="${H(p.detail)}">Последний обработанный файл: ${H(name)}</div>`:''}
  ${working&&Number.isFinite(Number(p.elapsed_seconds))?
    `<div class="run-status-hint">Выполняется: ${runDuration(p.elapsed_seconds)}
    ${approx?` · Предварительный прогноз: ещё ~${runDuration(eta)} (может меняться)`:''}</div>`:''}
  ${status==='completed_with_errors'||status==='failed'?
    `<div class="run-status-hint">${H(run?.error||'Подробности смотри во вкладке «Логи».')}</div>`:''}`;
}
async function pollRunProgress(){
  if(!state.me||state.tab!=='home'||!state.active||state.pollingRun)return;
  state.pollingRun=true;
  try{
    const id=state.active.id;
    const data=await api('/runs/'+encodeURIComponent(id));
    if(!state.active||state.active.id!==id||state.tab!=='home')return;
    const oldStatus=state.active.status;
    state.active=data;
    if(data.status!==oldStatus){await refresh();return}
    const node=document.getElementById('runProgressCard');
    if(node)node.innerHTML=runProgressCard(data);
  }catch(error){console.warn('Progress poll:',error)}
  finally{state.pollingRun=false}
}
function home(){const latest=state.active,progress=latest?.progress||{},running=latest&&['queued','running','stopping'].includes(latest.status),installed=state.model?.models?.[0]?.available;return `<div class="eyebrow">РАБОЧЕЕ ПРОСТРАНСТВО</div><h1 class="heading">Новая сортировка</h1><p class="sub">Загрузи ФО, один раз подготовь библиотеку Образцов и запусти MegaLoc.</p>${banner()}
<div class="grid"><section class="panel"><div class="line"><h2>01 · Фотографии отчёта</h2><span class="pill">${Number(state.batchInfo.photos)||0} ФО</span></div><p>Выбери целую папку ФО на компьютере. Передача на сервер возобновляемая.</p><label class="file-label"><input type="file" id="foFiles" multiple webkitdirectory directory onchange="uploadFiles('fo',this.files)"><b>↑ Загрузить папку ФО</b><span class="hint">Или выбери несколько фотографий</span></label><button class="button" onclick="newBatch()">Создать новую партию</button><div class="hint" style="margin-top:12px">Партия: ${H(state.batch||'не создана')}</div></section>
<section class="panel"><div class="line"><h2>02 · Библиотека Образцов</h2><span class="pill">${state.references.total} Образцов</span></div><p>Загрузи папку с подпапками SAM-0001, SAM-0002 и т.д. Кэш эмбеддингов создаётся автоматически после группировки ФО.</p><label class="file-label"><input type="file" id="refFiles" multiple webkitdirectory directory onchange="uploadFiles('reference',this.files)"><b>↑ Загрузить папку Образцов</b><span class="hint">SAM-xxxx/фото.jpg</span></label><div class="hint">Конструкций: ${state.references.sam.length} · Образцы сохраняются на VPS</div></section></div>
${state.uploading?`<section class="panel"><div class="line"><b>Передача файлов</b><b id="uploadPercent">${state.uploadPercent}%</b></div><div class="bar" id="uploadBar"><span style="width:${state.uploadPercent}%"></span></div><div class="hint" id="uploadLabel">${H(state.uploadLabel)}</div></section>`:''}
<section class="panel"><div class="line"><div><h2>03 · Распознавание</h2><p>Один движок — MegaLoc. CPU Worker отдельно от сайта.</p></div><span class="pill">${installed?'● Модель готова':'○ Нет модели'}</span></div>${!installed?`<button class="button" onclick="downloadModel()">Скачать MegaLoc</button><span class="hint">　${H(state.model?.downloads?.megaloc?.message||'Веса ещё не скачаны')}</span>`:''}<div class="section"><div class="line"><b>Порог группировки ФО</b><strong id="thresholdValue">${state.threshold.toFixed(2)}</strong></div><input type="range" min="0.50" max="0.99" step="0.01" value="${state.threshold}" oninput="setThreshold(this.value)"><p>Рабочее значение 0.50. Алгоритм группировки и сопоставления не изменён.</p></div></section>
<section class="panel" id="runProgressCard">${runProgressCard(latest)}</section>`}
function setThreshold(v){state.threshold=Number(v);document.getElementById('thresholdValue').textContent=state.threshold.toFixed(2)}
async function newBatch(){if(state.uploading)return;try{const data=await api('/batches',{method:'POST'});state.batch=data.batch_id;localStorage.setItem('ps.batch',state.batch);await refresh()}catch(e){report(e)}}
async function downloadModel(){try{await api('/models/megaloc/download',{method:'POST'});await refresh()}catch(e){report(e)}}
async function startRun(){try{await api('/runs',jopts({batch_id:state.batch,grouping_threshold:state.threshold}));await refresh()}catch(e){report(e)}}
async function stopRun(){try{await api('/runs/'+state.active.id+'/stop',{method:'POST'});await refresh()}catch(e){report(e)}}
async function signout(){await api('/auth/logout',{method:'POST'});state.me=null;clearInterval(state.runTimer);clearInterval(state.fullTimer);renderLogin()}
const imageKinds=['jpg','jpeg','png','webp','bmp','tif','tiff'];
function refSam(path){const parts=path.replaceAll('\\','/').split('/');return parts.find(p=>/^SAM-\d{4}(?!\d)(?=$|[- ,;\t(])/i.test(p))||''}
// 12 concurrent files; single-request fast path with resumable PATCH fallback.
const UPLOAD_WORKERS=12, UPLOAD_CHUNK_BYTES=16*1024*1024, UPLOAD_MAX_FILE_BYTES=60*1024*1024;
const uploadSleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function retryableUploadError(error){
  const msg=String(error?.message||error);
  return error instanceof TypeError || /^HTTP (409|429|5\d\d)\b/.test(msg) ||
    /Failed to fetch|NetworkError|Load failed/i.test(msg);
}
async function uploadFiles(kind,input){
  const files=Array.from(input||[]).filter(f=>imageKinds.includes(f.name.split('.').pop().toLowerCase()));
  if(!files.length)return report('Не найдены изображения');
  if(state.uploading)return;
  state.uploading=true;
  state.uploadPercent=0;
  state.uploadLabel='Подготовка загрузки…';
  state.error='';
  try{
    if(kind==='fo'&&!state.batch){
      const batch=await api('/batches',{method:'POST'});
      state.batch=batch.batch_id;
      localStorage.setItem('ps.batch',state.batch);
    }
    render();
    const total=files.reduce((sum,file)=>sum+file.size,0);
    const credited=new Array(files.length).fill(0);
    const started=performance.now();
    let cursor=0, completed=0, lastPaint=0;
    const errors=[];
    const stageMetrics={direct:{count:0,ms:0},init:{count:0,ms:0},transfer:{count:0,ms:0},finish:{count:0,ms:0}};
    async function trackedUploadApi(stage,url,opts){
      const startedAt=performance.now();
      try{return await api(url,opts)}
      finally{stageMetrics[stage].count++;stageMetrics[stage].ms+=performance.now()-startedAt}
    }
    function updateProgress(force=false){
      const now=performance.now();
      if(!force&&now-lastPaint<150)return;
      lastPaint=now;
      const bytes=credited.reduce((sum,x)=>sum+x,0);
      const elapsed=Math.max((now-started)/1000,0.001);
      const rate=bytes/elapsed;
      const remaining=rate>0?Math.ceil((total-bytes)/rate):null;
      state.uploadPercent=total?Math.min(100,Math.floor(100*bytes/total)):100;
      const mib=n=>(n/1048576).toFixed(1);
      state.uploadLabel=completed+'/'+files.length+' файлов · '+mib(bytes)+' / '+mib(total)+' МБ · '+mib(rate)+' МБ/с'+
        (remaining===null?'':' · осталось ~'+Math.ceil(remaining/60)+' мин');
      const bar=document.querySelector('#uploadBar span');
      const label=document.getElementById('uploadLabel');
      const percent=document.getElementById('uploadPercent');
      if(bar)bar.style.width=state.uploadPercent+'%';
      if(label)label.textContent=state.uploadLabel;
      if(percent)percent.textContent=state.uploadPercent+'%';
    }
    async function uploadOne(file,index){
      const relative=file.webkitRelativePath||file.name;
      const sam=kind==='reference'?refSam(relative):null;
      if(kind==='reference'&&!sam)throw Error('Невозможно определить SAM для '+relative);
      if(file.size>UPLOAD_MAX_FILE_BYTES)throw Error('Файл больше 60 МБ: '+relative);
      const key=['ps-upload',kind,state.batch,relative,file.size,file.lastModified].join(':');
      let id=localStorage.getItem(key), offset=0;
      if(id){
        try{
          const status=await api('/uploads/'+encodeURIComponent(id));
          if(status.finalized){
            localStorage.removeItem(key);
            credited[index]=file.size;completed++;updateProgress(true);
            return;
          }
          offset=Number(status.offset);
          if(!Number.isInteger(offset)||offset<0||offset>file.size)throw Error('Неверный offset');
        }catch(error){
          if(!/^HTTP (404|410)\b/.test(String(error?.message||error)))throw error;
          localStorage.removeItem(key);
          id=null;
        }
      }
      if(!id){
        // Stable client ID is stored before transfer: an interrupted direct PUT
        // resumes through the existing offset-based PATCH API after a reload.
        id=crypto.randomUUID();
        localStorage.setItem(key,id);
        const params=new URLSearchParams({
          kind,filename:file.name,size:String(file.size),
          batch_id:kind==='fo'?state.batch:'',sam:sam||''
        });
        try{
          await trackedUploadApi('direct','/uploads/direct/'+encodeURIComponent(id)+'?'+params,{
            method:'PUT',headers:{'Content-Type':'application/octet-stream'},body:file
          });
          localStorage.removeItem(key);
          credited[index]=file.size;completed++;updateProgress(true);
          return;
        }catch(error){
          if(!retryableUploadError(error))throw error;
          try{
            const status=await api('/uploads/'+encodeURIComponent(id));
            if(status.finalized){
              localStorage.removeItem(key);
              credited[index]=file.size;completed++;updateProgress(true);
              return;
            }
            offset=Number(status.offset);
            if(!Number.isInteger(offset)||offset<0||offset>file.size)
              throw Error('Неверный offset');
          }catch(statusError){
            if(!/^HTTP (404|410)\b/.test(String(statusError?.message||statusError)))throw statusError;
            // The server has no partial transfer. Use the old resumable route.
            id=null;
            localStorage.removeItem(key);
          }
        }
      }
      if(!id){
        const result=await trackedUploadApi('init','/uploads',jopts({kind,filename:file.name,size:file.size,
          batch_id:kind==='fo'?state.batch:null,sam}));
        id=result.id;
        localStorage.setItem(key,id);
      }
      credited[index]=offset;updateProgress(true);
      let failures=0;
      while(offset<file.size){
        const end=Math.min(offset+UPLOAD_CHUNK_BYTES,file.size);
        try{
          const result=await trackedUploadApi('transfer','/uploads/'+encodeURIComponent(id),{
            method:'PATCH',headers:{'Upload-Offset':String(offset),'Content-Type':'application/octet-stream'},
            body:file.slice(offset,end)
          });
          const confirmed=Number(result.offset);
          if(!Number.isInteger(confirmed)||confirmed<=offset||confirmed>end)
            throw Error('Неверный ответ сервера о размере блока');
          offset=confirmed;
          failures=0;
        }catch(error){
          if(!retryableUploadError(error)||++failures>3)throw error;
          await uploadSleep(failures*400);
          // Lost response? Ask the server how many bytes it really saved.
          try{
            const status=await api('/uploads/'+encodeURIComponent(id));
            const confirmed=Number(status.offset);
            if(Number.isInteger(confirmed)&&confirmed>=0&&confirmed<=file.size)offset=confirmed;
          }catch{}
        }
        credited[index]=offset;
        updateProgress();
      }
      await trackedUploadApi('finish','/uploads/'+encodeURIComponent(id)+'/finish',{method:'POST'});
      localStorage.removeItem(key);
      credited[index]=file.size;completed++;updateProgress(true);
    }
    async function worker(){
      while(cursor<files.length){
        const index=cursor++;
        try{await uploadOne(files[index],index)}
        catch(error){errors.push(files[index].name+': '+String(error?.message||error))}
      }
    }
    await Promise.all(Array.from({length:Math.min(UPLOAD_WORKERS,files.length)},()=>worker()));
    updateProgress(true);
    const seconds=(performance.now()-started)/1000;
    const overallMbit=seconds>0?((credited.reduce((sum,x)=>sum+x,0)*8)/seconds/1e6).toFixed(1):'0';
    console.info('[PhotoSorter upload] '+JSON.stringify({files:files.length,parallel:Math.min(UPLOAD_WORKERS,files.length),totalMbitPerSecond:overallMbit,elapsedSeconds:seconds.toFixed(1),stages:Object.fromEntries(Object.entries(stageMetrics).map(([name,data])=>[name,{requests:data.count,averageMs:data.count?Math.round(data.ms/data.count):0}]))}));
    if(errors.length)throw Error('Не загружено '+errors.length+' из '+files.length+' файлов: '+errors.slice(0,3).join('; '));
    state.uploadLabel='Загружено '+completed+' файлов';
  }catch(error){
    state.error=String(error?.message||error);
  }finally{
    state.uploading=false;
    await refresh();
  }
}
function results(){const r=state.active,rows=state.results?.rows||[],sams=state.results?.sam_counts||{};return `<div class="eyebrow">РЕЗУЛЬТАТЫ ОБРАБОТКИ</div><h1 class="heading">Готовые фотографии</h1><p class="sub">Группы ФО, назначения SAM и выгрузка ZIP.</p>${banner()}<section class="panel"><div class="line"><select style="max-width:380px" onchange="selectRun(this.value)">${state.runs.map(x=>`<option value="${H(x.id)}" ${x.id===r?.id?'selected':''}>${H(x.id)} — ${H(x.status)}</option>`).join('')}</select>${r?.models?.megaloc?.status==='completed'?`<a href="/api/download/${r.id}" class="button primary">↓ Скачать все ZIP</a>`:''}</div></section>${!rows.length?'<div class="panel"><p>Нет готовых результатов. Выбери завершённый запуск.</p></div>':`<div class="meters"><div class="metric"><b>${rows.length}</b><small>ФО</small></div><div class="metric"><b>${new Set(rows.map(x=>x.group_id)).size}</b><small>Групп</small></div><div class="metric"><b>${rows.filter(x=>x.assigned_sam==='_Неопределено').length}</b><small>Неопределено</small></div></div><div class="tabline"><button class="button ${state.resultMode==='sam'?'active':''}" onclick="state.resultMode='sam';render()">По SAM</button><button class="button ${state.resultMode==='groups'?'active':''}" onclick="state.resultMode='groups';render()">Группы ФО</button></div>${resultGroups(rows,sams)}`}`}
function resultGroups(rows,sams){const isSam=state.resultMode==='sam';const groups={};for(const row of rows){const key=isSam?row.assigned_sam:(row.group_id||'Без группы');(groups[key]??=[]).push(row)}return Object.keys(groups).sort().map(key=>`<section class="panel"><div class="line"><div><h2>${H(key)}</h2><span class="hint">${groups[key].length} ФО</span></div>${isSam?`<a class="button" href="/api/download/${state.active.id}?sam=${encodeURIComponent(key)}">↓ ZIP</a>`:''}</div><div class="run-grid">${groups[key].map(row=>{const i=rows.indexOf(row);return `<article class="photo"><img loading="lazy" src="/api/images/${state.active.id}/megaloc/${i}" alt="ФО"><div class="details">${isSam?`<b>${H(row.assigned_sam)}</b><br>`:`<b>Группа ${H(row.group_id)}</b><br>`}<span class="muted">${H(row.query?.split(/[\\/]/).pop())}</span><br>${isSam?'Оценка: '+(Number(row.score)||0).toFixed(3):'Из группы ФО'}</div></article>`}).join('')}</div></section>`).join('')}
function selectRun(id){state.active=state.runs.find(x=>x.id===id)||null;state.results=null;refresh()}
function logs(){return `<div class="eyebrow">ДИАГНОСТИКА ОБРАБОТКИ</div><h1 class="heading">Логи</h1><p class="sub">События API и MegaLoc Worker.</p>${banner()}<section class="panel"><select onchange="selectRun(this.value)">${state.runs.map(x=>`<option value="${H(x.id)}" ${x.id===state.active?.id?'selected':''}>${H(x.id)} — ${H(x.status)}</option>`).join('')}</select><div style="margin-top:18px">${state.logs.length?state.logs.map(x=>`<div class="log"><time>${H(fmt(x.at))}</time><strong>${H(x.level)}</strong><span>${H(x.message)}</span></div>`).join(''):'<p class="hint">Событий пока нет.</p>'}</div></section>`}
boot();
