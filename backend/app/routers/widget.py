from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from uuid import UUID

router = APIRouter(tags=["Widget"])


@router.get("/chatbot-iframe/{agent_id}", response_class=HTMLResponse)
async def widget_frame(agent_id: UUID):
    """Serve the isolated, lightweight iframe used by the embed loader."""
    return HTMLResponse(f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI assistant</title><style>
*{{box-sizing:border-box}}body{{margin:0;font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#242532;background:#fff}}.app{{height:100dvh;display:flex;flex-direction:column}}header{{padding:17px 18px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #eeeef4}}.mark{{width:34px;height:34px;border-radius:10px;background:#6358df;color:#fff;display:grid;place-items:center;font-size:17px}}header b{{display:block;font-size:14px}}header small{{display:block;margin-top:3px;color:#8b8d99;font-size:11px}}.messages{{flex:1;overflow:auto;padding:18px;display:flex;flex-direction:column;gap:14px}}.message{{max-width:88%;padding:11px 13px;border-radius:4px 12px 12px 12px;background:#f4f5f8;font-size:13px;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}}.message.user{{align-self:flex-end;background:#6358df;color:#fff;border-radius:12px 4px 12px 12px}}.suggestions{{padding:0 14px 10px;display:flex;flex-wrap:wrap;gap:6px}}.suggestions button{{border:1px solid #e4e2fb;background:#fff;border-radius:20px;padding:7px 10px;color:#5d53d3;font-size:11px}}form{{margin:0 12px 8px;padding:8px;border:1px solid #e3e4eb;border-radius:10px;display:flex;gap:8px}}input{{border:0;outline:0;min-width:0;flex:1;font-size:13px}}form button{{border:0;border-radius:7px;background:#6358df;color:#fff;width:32px;height:32px;font-size:17px}}footer{{text-align:center;padding:3px 0 10px;color:#a3a5ae;font-size:10px}}.error{{color:#b54747}}.typing{{color:#888;font-size:12px}}
</style></head><body><div class="app"><header><div class="mark">✦</div><div><b id="agentName">AI assistant</b><small>Typically replies in a few seconds</small></div></header><div class="messages" id="messages"><div class="message">Hi! How can I help you today?</div></div><div class="suggestions" id="suggestions"></div><form id="form"><input id="input" placeholder="Type your message…" autocomplete="off"/><button aria-label="Send">↑</button></form><footer>Powered by Orbit</footer></div>
<script>
const agentId={str(agent_id)!r};const params=new URLSearchParams(location.search);const api=(params.get('backend')||location.origin).replace(/\\/$/,'');let conversationId='';const messages=document.getElementById('messages');const input=document.getElementById('input');let busy=false;
function add(text,role='assistant',cls=''){{const el=document.createElement('div');el.className='message '+role+(cls?' '+cls:'');el.textContent=text;messages.appendChild(el);messages.scrollTop=messages.scrollHeight;return el}}
async function send(text){{text=(text||'').trim();if(!text||busy)return;add(text,'user');input.value='';busy=true;const pending=add('Thinking…','assistant','typing');try{{const res=await fetch(api+'/api/v2/agents/'+agentId+'/chat',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{message:text,conversationId:conversationId||undefined,stream:true}})}});if(!res.ok)throw new Error('The assistant is temporarily unavailable ('+res.status+').');conversationId=res.headers.get('X-Conversation-Id')||conversationId;pending.remove();const answer=add('','assistant');const reader=res.body.getReader();const decoder=new TextDecoder();let buffer='';while(true){{const{{value,done}}=await reader.read();if(done)break;buffer+=decoder.decode(value,{{stream:true}});const events=buffer.split('\\n\\n');buffer=events.pop()||'';for(const event of events){{const data=event.split('\\n').filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trim()).join('\\n');if(!data||data==='[DONE]')continue;try{{const obj=JSON.parse(data);if(obj.type==='text-delta')answer.textContent+=obj.delta||'';else if(obj.type==='error')answer.textContent=obj.errorText||'Something went wrong.'}}catch{{}}}}messages.scrollTop=messages.scrollHeight}}if(!answer.textContent)answer.textContent='I could not generate a response. Please try again.'}}catch(e){{pending.textContent=e.message;pending.classList.add('error')}}finally{{busy=false;input.focus()}}}}
document.getElementById('form').addEventListener('submit',e=>{{e.preventDefault();send(input.value)}});window.addEventListener('message',event=>{{if(event.source!==parent||!event.data||typeof event.data!=='object')return;if(event.data.type==='IDENTIFY_USER'){{/* identity is accepted for future signed-user support */}}if(event.data.type==='TOOL_RESULT'){{parent.postMessage({{type:'TOOL_RESULT_ACK',toolCallId:event.data.toolCallId}},api)}}}});
fetch(api+'/api/v2/agents/'+agentId).then(r=>r.ok?r.json():null).then(agent=>{{if(!agent)return;document.getElementById('agentName').textContent=agent.name||'AI assistant';messages.innerHTML='';add((agent.initial_messages||[])[0]||'Hi! How can I help you today?');const row=document.getElementById('suggestions');(agent.suggested_messages||[]).slice(0,3).forEach(q=>{{const b=document.createElement('button');b.textContent=q;b.addEventListener('click',()=>send(q));row.appendChild(b)}})}}).catch(()=>{{}});
</script></body></html>''')


@router.get("/widget.js")
async def widget_loader():
    """Return a dependency-free embed loader so the widget works from a deployed API URL."""
    from fastapi.responses import Response
    js = r'''(function(){
  var s=document.currentScript,agent=s&&(s.dataset.agentId||s.id)||window.orbitAgentId||"",api=(s&&s.dataset.backendUrl)||new URL(s.src).origin;
  if(!agent){console.warn("Orbit widget: add data-agent-id to the script tag.");return;}
  var b=document.createElement("button");b.type="button";b.setAttribute("aria-label","Open AI assistant");b.textContent="✦";Object.assign(b.style,{position:"fixed",right:"22px",bottom:"22px",width:"56px",height:"56px",border:0,borderRadius:"50%",background:"#6358df",color:"white",fontSize:"24px",boxShadow:"0 5px 20px #25224a30",cursor:"pointer",zIndex:2147483000});
  var f=document.createElement("iframe");f.title="AI assistant";f.src=api+"/chatbot-iframe/"+encodeURIComponent(agent)+"?backend="+encodeURIComponent(api);Object.assign(f.style,{position:"fixed",right:"22px",bottom:"90px",width:"390px",height:"590px",maxWidth:"calc(100vw - 28px)",maxHeight:"calc(100vh - 110px)",border:"1px solid #e7e7ef",borderRadius:"16px",background:"white",boxShadow:"0 12px 40px #25224a20",zIndex:2147483000,display:"none"});
  var open=false;b.addEventListener("click",function(){open=!open;f.style.display=open?"block":"none";b.textContent=open?"×":"✦";});document.body.appendChild(b);document.body.appendChild(f);
})();'''
    return Response(content=js, media_type="application/javascript", headers={"Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"})
