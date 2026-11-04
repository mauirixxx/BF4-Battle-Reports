const form=document.getElementById('player-selection');
if(form){
 const picks=[...form.querySelectorAll('.player-pick')];
 const buttons=[...form.querySelectorAll('[data-player-action]')];
 const count=document.getElementById('selected-count');
 function refresh(){const n=picks.filter(p=>p.checked).length;count.textContent=n+' players selected';buttons.forEach(b=>b.disabled=n<2);}
 picks.forEach(p=>p.addEventListener('change',refresh));
 form.addEventListener('submit',event=>{if(picks.filter(p=>p.checked).length<2){event.preventDefault();return;}});
 refresh();
}
