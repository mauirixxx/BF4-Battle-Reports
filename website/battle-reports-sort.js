document.querySelectorAll('.sortable-scoreboard').forEach(table => {
  const tbody = table.tBodies[0];
  const headings = Array.from(table.tHead.rows[0].cells);
  let current = 4, ascending = false;
  const numeric = index => index !== 0;
  const value = (row, index) => {
    const raw = row.cells[index].textContent.trim();
    return numeric(index) ? Number(raw.replace(/,/g, '').replace('%', '').replace('∞', '999999')) : raw.toLocaleLowerCase();
  };
  function sort(index, asc) {
    const rows = Array.from(tbody.rows);
    rows.sort((a,b) => {
      const x=value(a,index), y=value(b,index);
      const cmp=numeric(index) ? x-y : x.localeCompare(y);
      return asc ? cmp : -cmp;
    });
    tbody.replaceChildren(...rows);
    current=index; ascending=asc;
    headings.forEach((th,i)=>{
      const button=th.querySelector('button');
      button.querySelector('span').textContent = i===index ? (asc?' ▲':' ▼') : '';
      th.setAttribute('aria-sort',i===index ? (asc?'ascending':'descending') : 'none');
    });
  }
  headings.forEach((th,index)=>{
    const label=th.textContent.trim();
    const button=document.createElement('button');
    button.type='button';
    button.className='sort-button';
    button.textContent=label;
    const arrow=document.createElement('span');
    button.appendChild(arrow);
    th.replaceChildren(button);
    button.addEventListener('click',()=>sort(index,index===current ? !ascending : index===0));
  });
  sort(4,false);
});
