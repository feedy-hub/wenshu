'use strict';
$('#source-editor').onclick=action(()=>openSourceEditor());
async function openSourceEditor(file){
 const pid=project?.id||doc?.project_id;
 if(!pid)throw Error('当前 PDF 没有关联源稿，请先导入对应的 .tex 或项目 ZIP。');
 modal('<div class="dialog-eyebrow">MANUSCRIPT</div><h2>编辑源稿副本</h2><p id="editor-loading">正在读取源文件…</p>');
 $('#modal').classList.add('source-editor-dialog');
 let result;
 try{result=await api('/api/source-read',{project_id:pid,file})}catch(e){$('#editor-loading').textContent='读取失败：'+e.message;return}
 if(!$('#editor-loading'))return;
 project=result.project;
 let current=result,dirty=false;
 $('#modal-content').innerHTML=`<div class="dialog-eyebrow">MANUSCRIPT</div><h2>编辑源稿副本</h2><p class="hint">修改保存在本机项目副本。保存后编译，阅读视图才会更新。</p><select id="source-file" aria-label="源文件">${result.files.map(f=>`<option ${f===result.file?'selected':''}>${esc(f)}</option>`).join('')}</select><textarea id="source-code" aria-label="LaTeX 源代码" spellcheck="false"></textarea><div class="editor-footer"><span id="editor-state">已载入 · 版本 ${result.project.revision}</span><span class="spacer"></span><button id="source-save">保存副本</button><button id="source-save-compile" class="primary">保存并编译</button></div><p id="editor-message" role="status"></p>`;
 $('#source-code').value=result.text;
 $('#source-code').oninput=()=>{dirty=true;$('#editor-state').textContent='有未保存的修改'};
 $('#source-file').onchange=action(async()=>{if(dirty){$('#source-file').value=current.file;throw Error('请先保存当前文件，再切换文件。')}await openSourceEditor($('#source-file').value)});
 const save=async compile=>{const code=$('#source-code'),message=$('#editor-message'),saveButton=$('#source-save'),compileButton=$('#source-save-compile');saveButton.disabled=true;compileButton.disabled=true;try{message.textContent='正在保存…';const meta=await api('/api/source-save',{project_id:pid,file:current.file,text:code.value,revision:current.project.revision,hash:current.hash});project=meta;current=await api('/api/source-read',{project_id:pid,file:current.file});dirty=code.value!==current.text;$('#editor-state').textContent=dirty?'有未保存的修改':`已保存 · 版本 ${meta.revision}`;message.textContent='已保存。'+(compile?'正在打开编译选项…':'编译后可在阅读视图查看。');if(compile){$('#modal').classList.remove('source-editor-dialog');compileDialog()}}catch(e){message.textContent=e.message;message.className='warning'}finally{saveButton.disabled=false;compileButton.disabled=false}};
 $('#source-save').onclick=()=>save(false);$('#source-save-compile').onclick=()=>save(true);
 $('#modal').scrollTop=0;
}
$('#modal').addEventListener('close',()=>$('#modal').classList.remove('source-editor-dialog'));
