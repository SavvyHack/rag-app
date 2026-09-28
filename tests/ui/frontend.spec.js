const {test,expect} = require('@playwright/test');
const {pathToFileURL} = require('node:url');
const path = require('node:path');
const invoice = `The invoice lists the following transactions:

* **Invoice 1 (09/09/2026):** $40.50
* **Invoice 2 (16/09/2026):** $40.50
* **Invoice 3 (17/09/2026):** $54.00
* **Invoice 4 (23/09/2026):** $40.50
* **Invoice 5 (24/09/2026):** $63.00

The **total amount** is **$238.50**.

| Date | Invoice | Amount |
| --- | --- | ---: |
| 09 Sep 2026 | Invoice 1 | $40.50 |
| 17 Sep 2026 | Invoice 3 | $54.00 |
| **Total** | **5 invoices** | **$238.50** |

Sources supplied:
[1] Invoice Template 25-09.pdf — page 1`;
function fixture(content=invoice) {
  const chats=[{id:'one',title:'September invoice breakdown',notes:'',folder_id:'finances',updated:'2026-09-26T05:00:00Z'},{id:'two',title:'Project research',notes:'',folder_id:null,updated:'2026-09-25T05:00:00Z'}];
  return {revision:1,chat:chats[0],chats,folders:[{id:'finances',name:'Finances',chat_count:1},{id:'research',name:'Research',chat_count:0}],folder:'all',documents:[{id:'doc1',name:'Invoice Template 25-09.pdf',chunk_count:1}],messages:[{id:1,role:'user',content:'How much money did I make?',status:'complete'},{id:2,role:'assistant',content,status:'complete'}],busy:false,ready:true,job:null,status:'Ready when you are',error:'',semantic:false,model:'balanced',context:8192,models:[{id:'balanced',label:'Balanced · Qwen3.5 2B · 1.28 GB'},{id:'light',label:'Light · Qwen3.5 0.8B · 533 MB'}]};
}
async function boot(page, initial=fixture()) {
  await page.addInitScript(s => {
    window.testState=s; window.actions=[];
    window.pywebview={api:{poll:async revision => revision === s.revision ? null : structuredClone(s), dispatch:async (name,payload) => {
      window.actions.push({name,payload});
      if(name==='create_folder'){s.folders.push({id:'new',name:payload.name,chat_count:0});s.folder='new';}
      if(name==='rename_folder')s.folders.find(f=>f.id===payload.id).name=payload.name;
      if(name==='select_folder')s.folder=payload.id;
      if(name==='move_chat'){s.chat.folder_id=payload.id||null;s.chats.find(c=>c.id===s.chat.id).folder_id=s.chat.folder_id;s.folder=payload.id||'unfiled';}
      if(name==='delete_folder'){s.folders=s.folders.filter(f=>f.id!==payload.id);s.chats.filter(c=>c.folder_id===payload.id).forEach(c=>c.folder_id=null);s.chat=s.chats.find(c=>c.id===s.chat.id);s.folder='unfiled';}
      if(name==='select_chat'){s.chat=s.chats.find(c=>c.id===payload.id);s.messages=[];}
      if(name==='new_chat'){const c={id:'newchat',title:'New chat',notes:'',folder_id:['all','unfiled'].includes(s.folder)?null:s.folder,updated:new Date().toISOString()};s.chats.push(c);s.chat=c;s.messages=[];}
      if(name==='send'){s.messages.push({id:88,role:'user',content:payload.text,status:'complete'},{id:89,role:'assistant',content:'',status:'streaming'});s.busy=true;s.job='answer';}
      if(name==='set_mode'){s.chat.mode=payload.mode;s.chat.workspace='C:/Local workspace';}
      if(name==='approve_tool'||name==='reject_tool'){s.activity.events.find(e=>e.id===payload.id).status=name==='approve_tool'?'approved':'rejected';}
      if(name==='undo_edit'){s.activity.events.find(e=>e.id===payload.id).status='undone';}
      if(name==='offline_only')s.offline_only=payload.enabled;
      if(name==='stop'){s.busy=false;s.job=null;s.messages.at(-1).status='stopped';}
      for(const f of s.folders)f.chat_count=s.chats.filter(c=>c.folder_id===f.id).length;
      s.revision++;return {ok:true,state:structuredClone(s)};
    }}};
  },initial);
  await page.goto(pathToFileURL(path.resolve('web/index.html')).href);
  await expect(page.locator('#chat-title')).toHaveText(initial.chat.title);
}

test('invoice emphasis, lists, currency, tables, sources and offline layout',async({page})=>{
  const requests=[];page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});
  await boot(page);
  await expect(page.locator('.assistant strong').filter({hasText:'Invoice 1'})).toBeVisible();
  await expect(page.locator('.assistant li')).toHaveCount(5);
  await expect(page.locator('.assistant .katex')).toHaveCount(0);
  await expect(page.locator('.assistant table')).toBeVisible();
  await expect(page.locator('.sources')).toContainText('Invoice Template 25-09.pdf');
  expect(requests).toEqual([]);
  await page.screenshot({path:'build/ui-invoice.png',fullPage:true});
});
test('LaTeX delimiters, aligned equations, fenced math and malformed math',async({page})=>{
  const source=String.raw`Inline $E=mc^2$ and \(\frac{a}{b}\).

$$\sum_{i=1}^{n} i = \frac{n(n+1)}{2}$$

\[\int_0^1 x^2\,dx = \frac{1}{3}\]

\begin{aligned}a&=b+c\\d&=e+f\end{aligned}

`+'```latex\n\\sqrt{x^2+y^2}\n```\n\n'+String.raw`Malformed $\frac{1}{$ still leaves the rest of the response readable.`;
  await boot(page,fixture(source));
  await expect(page.locator('.assistant .katex')).toHaveCount(6);
  await expect(page.locator('.katex-error')).toHaveCount(1);
  await expect(page.locator('.assistant')).toContainText('rest of the response readable');
  await page.screenshot({path:'build/ui-math.png',fullPage:true});
});
test('code highlighting, entities, quotes, task lists, and literal delimiters in code',async({page})=>{
  await boot(page,fixture('## Result\n\n**Invoice&#x20;one** &amp; two\n\n> A useful note.\n\n- [x] Complete\n- [ ] Remaining\n\n```python\nprint("$x$ **literal**")\n```\n\nInline `\\(x\\)` remains code.'));
  await expect(page.locator('.assistant h2')).toHaveText('Result');
  await expect(page.locator('.assistant strong')).toHaveText('Invoice one');
  await expect(page.locator('.assistant blockquote')).toContainText('A useful note');
  await expect(page.locator('.hljs-string')).toBeVisible();
  await expect(page.locator('.assistant .katex')).toHaveCount(0);
  await expect(page.locator('.assistant li').first()).toContainText('☑');
  await expect(page.getByRole('button',{name:'Copy code'})).toBeVisible();
});
test('model output cannot execute scripts or request remote resources',async({page})=>{
  const requests=[];page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});
  await boot(page,fixture('<script>window.pwned=true</script>\n<img src="https://example.com/track" onerror="window.pwned=true">\n\n[bad](javascript:alert(1)) ![remote](https://example.com/pixel)\n\n$\\href{javascript:alert(1)}{bad}$'));
  expect(await page.evaluate(()=>window.pwned)).toBeUndefined();
  await expect(page.locator('.assistant script,.assistant img,.assistant iframe')).toHaveCount(0);
  await expect(page.locator('.assistant a[href^="javascript"]')).toHaveCount(0);
  expect(requests).toEqual([]);
});
test('folder create, rename, move, filter, search, and deletion keep chats',async({page})=>{
  await boot(page);
  await page.getByRole('button',{name:'New folder',exact:true}).click();
  await page.getByLabel('Folder name').fill('Invoices');
  await page.getByRole('button',{name:'Save',exact:true}).click();
  await expect(page.locator('#chats')).toContainText('No chats here yet');
  await page.getByRole('button',{name:'Move',exact:true}).click();
  await page.getByLabel('Folder',{exact:true}).selectOption('new');
  await page.getByRole('button',{name:'Move chat',exact:true}).click();
  await expect(page.locator('#chats .chat-item')).toHaveCount(1);
  await page.getByRole('button',{name:'Manage Invoices'}).click();
  await page.getByRole('button',{name:'Rename folder'}).click();
  await page.getByLabel('Folder name').fill('Paid invoices');
  await page.getByRole('button',{name:'Save',exact:true}).click();
  await expect(page.locator('#breadcrumb')).toContainText('Paid invoices');
  await page.getByLabel('Search chats').fill('no-match');
  await expect(page.locator('#chats')).toContainText('No matching chats');
  await page.getByLabel('Search chats').fill('');
  await page.getByRole('button',{name:'Manage Paid invoices'}).click();
  await page.getByRole('button',{name:'Delete folder',exact:true}).click();
  await page.getByRole('button',{name:'Delete folder',exact:true}).click();
  await expect(page.locator('#chats .chat-item')).toHaveCount(2);
  await expect(page.locator('.assistant strong').first()).toBeVisible();
});
test('streaming markdown updates once, stopped replies render, and drafts survive switching',async({page})=>{
  await boot(page);
  await page.locator('#prompt').fill('A draft');
  await page.locator('[data-chat="two"]').click();
  await page.locator('[data-chat="one"]').click();
  await expect(page.locator('#prompt')).toHaveValue('A draft');
  await page.locator('#prompt').press('Enter');
  await expect(page.getByRole('button',{name:'Stop',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'New folder',exact:true})).toBeDisabled();
  for (const content of ['**Invoice', '**Invoice one**\n\nFirst line\nSecond line']) {
    await page.evaluate(text=>{const s=window.testState;s.messages.at(-1).content=text;s.revision++;window.LocalRAG.render(structuredClone(s));},content);
  }
  await expect(page.locator('.assistant strong')).toHaveText('Invoice one');
  await expect(page.locator('.assistant')).toContainText('Second line');
  await page.getByRole('button',{name:'Stop',exact:true}).click();
  await expect(page.locator('.assistant .message-status')).toHaveText('Stopped · saved');
  await expect(page.locator('.assistant strong')).toHaveCount(1);
});
test('long code and wide tables stay inside the conversation at minimum size',async({page})=>{
  await page.setViewportSize({width:860,height:620});
  await boot(page,fixture('```json\n{"long":"'+ 'x'.repeat(300)+'"}\n```\n\n| A | B | C | D | E | F | G | H |\n|---|---|---|---|---|---|---|---|\n|1|2|3|4|5|6|7|8|'));
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await expect(page.locator('#prompt')).toBeInViewport();
  await expect(page.locator('.copy-code')).toBeInViewport();
  await page.screenshot({path:'build/ui-narrow.png',fullPage:true});
});
test('reading older messages is not interrupted by streaming',async({page})=>{
  const s=fixture();s.messages=Array.from({length:16},(_,i)=>({id:i,role:i%2?'assistant':'user',content:'A previous message.\n\n'+invoice,status:'complete'}));s.messages.at(-1).status='streaming';s.busy=true;s.job='answer';
  await boot(page,s);
  await page.locator('#conversation').evaluate(el=>el.scrollTop=0);
  await page.evaluate(()=>{const s=window.testState;s.messages.at(-1).content+='\n\n**New text**';s.revision++;window.LocalRAG.render(structuredClone(s));});
  expect(await page.locator('#conversation').evaluate(el=>el.scrollTop)).toBe(0);
  await expect(page.locator('#jump-latest')).toBeVisible();
});

test('agent mode reveals the local workspace and offline workflows',async({page})=>{
  await boot(page);
  await page.getByLabel('Assistant mode').selectOption('agent');
  await expect(page.getByRole('complementary',{name:'Project workspace'})).toBeVisible();
  await expect(page.locator('#workspace-location')).toContainText('Local workspace');
  await page.getByRole('button',{name:'Workflows',exact:true}).click();
  await page.getByRole('button',{name:'Review a project',exact:true}).click();
  await expect(page.getByLabel('Assistant mode')).toHaveValue('plan');
  await expect(page.locator('#prompt')).toHaveValue(/Review the project/);
  await page.screenshot({path:'build/ui-workspace.png',fullPage:true});
});

test('pending edits need a deliberate review click and escape file contents',async({page})=>{
  const s=fixture();s.busy=true;s.job='agent';s.chat.mode='agent';s.chat.workspace='C:/Project';
  s.activity={runs:[{id:'run',status:'waiting',plan:'1. Read\n2. Propose\n3. Verify'}],events:[{id:'event1',name:'write_file',status:'pending',detail:{workspace:'C:/Project',summary:'Write index.html',path:'index.html',preview:'+<script>window.pwned=true</script>'}}]};
  await boot(page,s);
  await expect(page.locator('#workspace-panel')).toBeVisible();
  expect(await page.evaluate(()=>window.actions.some(a=>a.name==='approve_tool'))).toBe(false);
  await page.getByRole('button',{name:'Review action'}).click();
  await expect(page.locator('.review-preview')).toContainText('<script>');
  expect(await page.evaluate(()=>window.pwned)).toBeUndefined();
  await page.screenshot({path:'build/ui-review.png',fullPage:true});
  await page.getByRole('button',{name:'Apply change',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.actions.at(-1))).toEqual({name:'approve_tool',payload:{id:'event1'}});
});

test('command review can reject without executing and stop remains available',async({page})=>{
  const s=fixture();s.busy=true;s.job='agent';
  s.activity={runs:[],events:[{id:'command1',name:'run_command',status:'pending',detail:{summary:'Run command',workspace:'C:/Project',preview:'python -m unittest'}}]};
  await boot(page,s);
  await expect(page.getByRole('button',{name:'Stop',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Review action'}).click();
  await expect(page.locator('#dialog-body')).toContainText('change files elsewhere');
  await page.getByRole('button',{name:'Reject',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.actions.at(-1))).toEqual({name:'reject_tool',payload:{id:'command1'}});
});

test('completed file edits expose undo and scanned attachments explain automatic OCR',async({page})=>{
  const s=fixture();s.activity={runs:[],events:[{id:'edit1',name:'write_file',status:'applied',detail:{summary:'Saved greeting.md',path:'greeting.md',preview:'+Hello'}}]};
  await boot(page,s);
  await page.getByRole('button',{name:'Workspace',exact:true}).click();
  await page.getByRole('button',{name:'Undo edit'}).click();
  await expect.poll(()=>page.evaluate(()=>window.actions.at(-1))).toEqual({name:'undo_edit',payload:{id:'edit1'}});
  await page.getByRole('button',{name:'Files · 1',exact:true}).click();
  await expect(page.locator('#dialog-body')).toContainText('read automatically with on-device OCR');
});
