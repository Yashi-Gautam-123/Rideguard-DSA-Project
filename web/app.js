const $ = (s) => document.querySelector(s);
const state = { data: null, selected: null, replaying: false, historyVisible: false, history: [], replayRecord: null, replayIndex: 0 };
const statusKind = (s) => s === 'Normal Journey' ? 'normal' : s.includes('Multiple') ? 'danger' : s.includes('temporarily unavailable') || s.includes('device unavailable') ? 'caution' : s.includes('deviation') || s.includes('Speed') ? 'warn' : 'normal';
const shortStatus = (s) => ({'Normal Journey':'Normal','Location temporarily unavailable':'Location interruption','Route deviation detected':'Route deviation','Speed anomaly detected':'Speed anomaly','Driver device unavailable':'Driver device offline','Passenger device unavailable':'Passenger device offline','Multiple anomalies detected':'Multiple anomalies'})[s] || s;
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function request(path, data) { const r = await fetch(path, data ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)} : {}); if(!r.ok) throw new Error('Request failed'); return r.json(); }
function renderMetrics(data) {
  const n=data.trips.length, normal=data.trips.filter(t=>statusKind(t.status)==='normal').length, alert=n-normal;
  const cards=[['Active trips',n,'currently monitored','▦',''],['Normal journeys',normal,'within expected conditions','✓',''],['Trips needing attention',alert,'active safety indicators','⚑',alert?'warning':''],['Safe points nearby',data.graph.safe_places.length,'sample locations in network','✚','']];
  $('#metrics').innerHTML=cards.map(([label,value,note,icon,cls])=>`<div class="metric ${cls}"><div class="metric-top"><span>${label}</span><span class="metric-icon">${icon}</span></div><div class="metric-value">${value}<small>${note}</small></div></div>`).join('');
  const labels=['Normal Journey','Location temporarily unavailable','Driver device unavailable','Passenger device unavailable','Route deviation detected','Speed anomaly detected','Multiple anomalies detected'];
  const counts=Object.fromEntries(labels.map(label=>[label,data.trips.filter(t=>t.status===label).length]));
  $('#statusBreakdown').innerHTML=labels.map(label=>`<div class="status-count"><span class="status-chip ${statusKind(label)}">${escapeHtml(shortStatus(label))}</span><b>${counts[label]}</b></div>`).join('');
}
function renderRows(data) {
  const severity=s=>s.includes('Multiple')?5:s.includes('deviation')||s.includes('Speed')?4:s.includes('unavailable')?3:1;
  $('#tripRows').innerHTML=[...data.trips].sort((a,b)=>severity(b.status)-severity(a.status)).map(t=>`<tr data-id="${t.trip_id}" class="${state.selected===t.trip_id?'active':''}"><td><div class="trip-primary">${t.trip_id}</div><div class="trip-secondary">${t.taxi}</div></td><td><span class="status-chip ${statusKind(t.status)}">${escapeHtml(shortStatus(t.status))}</span></td><td>${escapeHtml(t.last_location.name)}</td><td>${t.speed_kmh?`${t.speed_kmh} <small>km/h</small>`:'—'}</td><td><span class="${t.driver_online?'device-dot':'device-off'}" title="Driver">●</span> <span class="${t.passenger_online?'device-dot':'device-off'}" title="Passenger">●</span></td><td class="row-arrow">›</td></tr>`).join('');
  $('#tripRows').querySelectorAll('tr').forEach(row=>row.addEventListener('click',()=>{state.selected=row.dataset.id;render(data)}));
  $('#tripCount').textContent=`${data.trips.length} active journeys`;
}
function coords(data) {
  const nodes=data.graph.nodes, xs=nodes.map(n=>n.lon), ys=nodes.map(n=>n.lat), minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
  const project=n=>({x:45+(n.lon-minX)/(maxX-minX)*530,y:35+(maxY-n.lat)/(maxY-minY)*350});
  return Object.fromEntries(nodes.map(n=>[n.id,project(n)]));
}
function renderMap(data, trip) {
  const xy=coords(data), nodes=Object.fromEntries(data.graph.nodes.map(n=>[n.id,n])); let svg='';
  for(const [a,adj] of Object.entries(data.graph.edges)) for(const b of Object.keys(adj)) if(a<b){const p=xy[a],q=xy[b];svg+=`<line x1="${p.x}" y1="${p.y}" x2="${q.x}" y2="${q.y}" stroke="#cbd6d0" stroke-width="5" stroke-linecap="round"/>`;}
  if(trip){const path=trip.route.map(id=>xy[id]).filter(Boolean);if(path.length>1)svg+=`<polyline points="${path.map(p=>`${p.x},${p.y}`).join(' ')}" fill="none" stroke="#30967d" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity=".72"/>`;const actual=(trip.updates||[]).map(u=>xy[u.node]).filter(Boolean);if(actual.length>1)svg+=`<polyline points="${actual.map(p=>`${p.x},${p.y}`).join(' ')}" fill="none" stroke="#db8b42" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`;}
  for(const p of data.graph.safe_places){const pos=xy[p.node];svg+=`<g transform="translate(${pos.x},${pos.y})"><circle r="10" fill="#fff" stroke="#77aa82" stroke-width="2"/><text text-anchor="middle" y="4" fill="#538d66" font-size="12" font-weight="bold">+</text></g>`;}
  if(trip){const pos=xy[trip.last_node];svg+=`<circle cx="${pos.x}" cy="${pos.y}" r="15" fill="#de8e43" opacity=".18"/><circle cx="${pos.x}" cy="${pos.y}" r="7" fill="#de8e43" stroke="white" stroke-width="3"/>`;}
  for(const node of data.graph.nodes){const p=xy[node.id], showLabel=!/^R\d+$/.test(node.id)||Number(node.id.slice(1))%15===0;svg+=`<g><circle cx="${p.x}" cy="${p.y}" r="${/^R\d+$/.test(node.id)?2.5:4}" fill="#92a69b"/>${showLabel?`<text x="${p.x+7}" y="${p.y-8}" fill="#71827b" font-size="9" font-family="DM Sans">${escapeHtml(node.name)}</text>`:''}</g>`;}
  $('#map').innerHTML=svg;
}
function renderDetail(data, trip) {
  if(!trip){$('#tripDetail').innerHTML='<p class="detail-value">No trip selected.</p>';return;}
  $('#detailSubtitle').textContent=`${trip.trip_id} · ${trip.taxi}`;
  $('#detailBadge').textContent=shortStatus(trip.status).toUpperCase(); $('#detailBadge').className=`status-chip ${statusKind(trip.status)}`;
  $('#mapSubtitle').textContent=`${trip.last_location.name} → ${trip.destination}`;
  const places=trip.safe_places.map(p=>`<div class="safe-row"><span>✚ ${escapeHtml(p.name)} <small>(${p.kind})</small></span><b>${p.distance_km} km</b></div>`).join('');
  const alert=trip.explanations.length?trip.explanations.map(escapeHtml).join('<br>'): 'No active anomaly. Conditions are within expected ranges.';
  const patterns=(trip.patterns||[]).map(escapeHtml).join('<br>')||'No rapid anomaly sequence detected.';
  $('#tripDetail').innerHTML=`<div class="detail-block"><div class="detail-label">LAST KNOWN POSITION</div><div class="detail-value">${escapeHtml(trip.last_location.name)}</div></div><div class="detail-block"><div class="detail-label">LAST SPEED</div><div class="detail-value">${trip.speed_kmh||'—'} km/h</div></div><div class="detail-block"><div class="detail-label">ALERT EXPLANATION</div><div class="detail-value">${alert}</div></div><div class="detail-block"><div class="detail-label">DEVICES</div><div class="detail-value">Driver ${trip.driver_online?'online':'offline'} · Passenger ${trip.passenger_online?'online':'offline'}</div></div><div class="detail-block" style="grid-column:1/-1"><div class="detail-label">PATTERN ANALYSIS</div><div class="detail-value">${patterns}</div></div><div class="detail-block" style="grid-column:1/-1"><div class="detail-label">NEAREST SAFE LOCATIONS · ROAD DISTANCE</div>${places||'<div class="safe-row">No safe places are reachable.</div>'}</div><div class="detail-block" style="grid-column:1/-1"><div class="detail-label">ALTERNATIVE ROUTE TO DESTINATION</div><div class="detail-value">${trip.alternative_route.map(id=>escapeHtml(data.graph.nodes.find(n=>n.id===id)?.name||id)).join(' → ')} · ${trip.alternative_distance_km??'—'} km remaining</div></div>`;
}
function renderTimeline(trip) {
  if(!trip || !trip.events.length){$('#timeline').innerHTML='<div class="event"><span class="event-time">—</span><i class="event-marker"></i><div><div class="event-title">Waiting for events</div><div class="event-text">Advance the simulation to receive trip updates.</div></div></div>';return;}
  $('#timeline').innerHTML=[...trip.events].reverse().slice(0,10).map(e=>`<div class="event ${e.kind.includes('raised')?'alert':''} ${e.detail.includes('offline')?'critical':''}"><span class="event-time">${new Date(e.time).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'})}</span><i class="event-marker"></i><div><div class="event-title">${escapeHtml(e.kind)}</div><div class="event-text">${escapeHtml(e.detail)}</div></div></div>`).join('');
}
function renderHistoryList() {
  $('#timeline').innerHTML=state.history.length?state.history.map((t,i)=>`<div class="history-card"><div><b>${escapeHtml(t.trip_id)} · ${escapeHtml(t.taxi)}</b>${new Date(t.completed_at).toLocaleString()} · ${escapeHtml(shortStatus(t.status))}</div><button class="subtle-btn" data-history-index="${i}">▶ Replay</button></div>`).join(''):'<div class="history-empty">No completed trips yet. Select an active trip and press “Finish trip” to save it here.</div>';
  $('#timeline').querySelectorAll('[data-history-index]').forEach(btn=>btn.addEventListener('click',()=>{state.replayRecord=state.history[Number(btn.dataset.historyIndex)];state.replayIndex=0;state.historyVisible=false;render(state.data);}));
}
function renderReplayFrame() {
  const record=state.replayRecord, updates=record.updates||[];
  if(!record||!state.data)return;
  const update=updates[Math.min(state.replayIndex,Math.max(0,updates.length-1))];
  const node=update&&state.data.graph.nodes.find(n=>n.id===update.node);
  const view={...record,updates:updates.slice(0,state.replayIndex+1),events:update?record.events.filter(e=>e.time<=update.time):record.events};
  if(update&&node){view.last_node=node.id;view.last_location=node;view.speed_kmh=update.speed_kmh;view.status=update.status||record.status;}
  $('#detailSubtitle').textContent=`${record.trip_id} · ${record.taxi} · Historical replay ${Math.min(state.replayIndex+1,updates.length)} of ${updates.length} updates`;
  $('#finishBtn').style.display='none';
  renderMap(state.data,view);renderDetail(state.data,view);renderTimeline(view);
}
function render(data) {
  state.data=data; if(!state.selected || !data.trips.some(t=>t.trip_id===state.selected)) state.selected=data.trips[0]?.trip_id;
  const trip=data.trips.find(t=>t.trip_id===state.selected); renderMetrics(data);renderRows(data);renderMap(data,trip);renderDetail(data,trip);renderTimeline(trip);
  $('#finishBtn').style.display=trip&&!state.replayRecord?'':'none';
  if(state.replayRecord)renderReplayFrame();
  if(state.historyVisible)renderHistoryList();
  $('#clock').textContent=`Simulation clock · ${new Date(data.clock).toLocaleString()}`;
  document.querySelectorAll('[data-scenario]').forEach(b=>b.classList.toggle('selected',b.dataset.scenario===data.scenario));
}
let timer=null;
async function load(){try{render(await request('./api/state'));}catch(e){$('#serverNotice').hidden=false;toast('Start Rideguard with run_rideguard.bat, then open the local address.');}}
function toast(message){const box=$('#toast');box.textContent=message;box.classList.add('show');setTimeout(()=>box.classList.remove('show'),2600)}
document.querySelectorAll('[data-scenario]').forEach(button=>button.addEventListener('click',async()=>{clearInterval(timer);state.replaying=false;state.replayRecord=null;state.historyVisible=false;try{render(await request('./api/scenario',{scenario:button.dataset.scenario}));toast(`Scenario loaded: ${button.textContent.trim()}`);}catch(e){toast('Could not load scenario. Start the Python server first.');}}));
$('#resetBtn').addEventListener('click',async()=>{clearInterval(timer);state.replaying=false;state.replayRecord=null;state.historyVisible=false;$('#replayBtn').textContent='▶ Replay';render(await request('./api/reset',{}));toast('Demo reset to its starting state.');});
$('#historyBtn').addEventListener('click',async()=>{clearInterval(timer);state.replaying=false;$('#replayBtn').textContent='▶ Replay';state.historyVisible=!state.historyVisible;state.replayRecord=null;if(state.historyVisible){try{state.history=(await request('./api/history')).history;}catch(e){toast('Could not load trip history.');}}render(state.data);});
$('#finishBtn').addEventListener('click',async()=>{if(!state.selected)return;try{const result=await request(`./api/finish/${encodeURIComponent(state.selected)}`,{});state.replayRecord=null;state.historyVisible=false;state.selected=null;render(result.state);toast('Trip saved to history.');}catch(e){toast('Could not finish this trip.');}});
$('#stepBtn').addEventListener('click',async()=>{clearInterval(timer);state.replaying=false;$('#replayBtn').textContent='▶ Replay';if(state.replayRecord){const count=(state.replayRecord.updates||[]).length;if(state.replayIndex+1<count){state.replayIndex++;renderReplayFrame();}return;}try{render(await request('./api/advance',{}));}catch(e){toast('Could not advance the simulation.');}});
$('#replayBtn').addEventListener('click',async()=>{if(state.replaying){clearInterval(timer);state.replaying=false;$('#replayBtn').textContent='▶ Replay';return;}state.replaying=true;$('#replayBtn').textContent='Ⅱ Pause';if(state.replayRecord){const count=(state.replayRecord.updates||[]).length;timer=setInterval(()=>{if(state.replayIndex+1>=count){clearInterval(timer);state.replaying=false;$('#replayBtn').textContent='▶ Replay';return;}state.replayIndex++;renderReplayFrame();},850);return;}timer=setInterval(async()=>{try{render(await request('./api/advance',{}));if(state.data.trips.every(t=>t.tick>=8)){clearInterval(timer);state.replaying=false;$('#replayBtn').textContent='▶ Replay';}}catch(e){clearInterval(timer);}},1100);});
$('#zoomBtn').addEventListener('click',()=>{if(state.data)renderMap(state.data,state.data.trips.find(t=>t.trip_id===state.selected));});
load();
